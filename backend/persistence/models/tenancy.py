"""
Multi-tenancy control-plane ("registry") schema — Phase 13.1.A.

These are the **control-plane** tables: the source of truth for *which*
tenants exist, *who* may reach them, and *where* each tenant's database
lives.  They hold routing and authorization only — **never tenant
business data and never tenant DB credentials** (those are dynamic
OpenBAO leases, see Phase 13.1.C).

Partition / collapse rules (see
``docs/planning/phase13-multi-tenancy-design.md`` §5):

  * Every table here is named ``registry_*``.  The prefix is the
    namespace: in the default single-DB homelab deployment these tables
    sit in the same database as the unprefixed tenant tables and the
    ``shared_*`` reference tables, and the prefix makes collisions
    structurally impossible.  The prefix is **stable across all
    deployment modes**, so a homelab user who later scales out to a
    dedicated registry database does not rename a single table.
  * **Foreign keys are allowed *within* the registry partition** (the
    grant/placement tables reference ``registry_tenant`` and
    ``registry_user``) because in every deployment these tables live in
    the *same* database.  A FK may **never** cross a partition boundary
    (e.g. a tenant table → ``registry_tenant``): that works collapsed
    but breaks the moment the registry is a separate database, so
    cross-partition references are *soft* (store the UUID, no
    ``ForeignKey``) and enforced in the app layer.

This module deliberately defines models on the shared ``Base`` so the
test suite's ``Base.metadata.create_all`` builds them on SQLite exactly
as production builds them via the ``registry`` Alembic chain.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# ---------------------------------------------------------------------
# Tenant tier values for registry_tenant_placement.tier.
#
# v3.0 GA ships ``silo`` only (database-per-tenant).  ``pool`` (shared
# DB + PostgreSQL RLS) is a designed-for-but-deferred SMB long-tail
# tier — the column exists so a tenant can be migrated between tiers
# later without a schema change.  See design doc §3.
# ---------------------------------------------------------------------
TENANT_TIER_SILO = "silo"
TENANT_TIER_POOL = "pool"
TENANT_TIERS = (TENANT_TIER_SILO, TENANT_TIER_POOL)

# Tenant lifecycle status values for registry_tenant.status.
TENANT_STATUS_ACTIVE = "active"
TENANT_STATUS_SUSPENDED = "suspended"
TENANT_STATUS_PROVISIONING = "provisioning"
TENANT_STATUSES = (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUS_PROVISIONING,
)


def _utcnow() -> datetime:
    """Naive-UTC timestamp, matching the federation models' convention.

    SQLite has no native tz-aware type, so the whole codebase stores
    naive-UTC datetimes; we mirror that here for cross-dialect parity.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RegistryTenant(Base):
    """A tenant (customer account) — the unit of isolation.

    In silo mode each tenant gets its own database (located via
    :class:`RegistryTenantPlacement`).  ``settings`` / ``limits`` hold
    per-account configuration and quotas (Phase 13.1.B).
    """

    __tablename__ = "registry_tenant"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default=TENANT_STATUS_ACTIVE)
    settings = Column(JSON, nullable=True)
    limits = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_registry_tenant_slug", "slug"),)


class RegistryUser(Base):
    """A global identity keyed by email — one identity, many tenants.

    Owns authn for non-SSO users (``password_hash`` nullable so SSO-only
    identities carry no local secret).  Tenant membership is expressed
    through :class:`RegistryUserTenantGrant`, never by a column here.
    """

    __tablename__ = "registry_user"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_registry_user_email", "email"),)


class RegistryUserTenantGrant(Base):
    """The explicit email→tenant mapping (1..*) — the least-privilege core.

    Carries the user's role within the tenant, a default-tenant flag for
    account switching, and an optional ``expires_at`` for **time-boxed /
    expiring** grants (the basis for enforced vendor-support access in
    Phase 13.1.E).  FKs are intra-partition and therefore allowed.
    """

    __tablename__ = "registry_user_tenant_grant"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        GUID(), ForeignKey("registry_user.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id = Column(
        GUID(), ForeignKey("registry_tenant.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(64), nullable=False, default="member")
    is_default = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_registry_grant_user_tenant"),
        Index("ix_registry_grant_user", "user_id"),
        Index("ix_registry_grant_tenant", "tenant_id"),
    )


class RegistryTenantPlacement(Base):
    """Per-tenant database **coordinates only** — never credentials.

    Tells the partition resolver which engine to build for a tenant.
    ``openbao_role`` names the OpenBAO database-secrets role that brokers
    dynamic credentials for this tenant (Phase 13.1.C); the password
    itself is never stored here or anywhere on disk.

    One placement per tenant for now (unique on ``tenant_id``).
    """

    __tablename__ = "registry_tenant_placement"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        GUID(), ForeignKey("registry_tenant.id", ondelete="CASCADE"), nullable=False
    )
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    dbname = Column(String(255), nullable=True)
    region = Column(String(64), nullable=True)
    tier = Column(String(16), nullable=False, default=TENANT_TIER_SILO)
    openbao_role = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_registry_placement_tenant"),
        Index("ix_registry_placement_tenant", "tenant_id"),
    )


class RegistryTenantEmailDomain(Base):
    """Per-tenant allowed email-domain allowlist (Phase 13.1.B, design §10).

    Enforced at provisioning time (invite / SSO-JIT / SCIM / grant
    creation): a user whose email domain is not in a tenant's allowlist
    cannot be added to that tenant.  An empty allowlist means "no domain
    restriction" — the tenant accepts any domain until it configures one.

    Domains are stored lowercased and bare (``example.com``, no ``@``).
    """

    __tablename__ = "registry_tenant_email_domain"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        GUID(), ForeignKey("registry_tenant.id", ondelete="CASCADE"), nullable=False
    )
    domain = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "domain", name="uq_registry_email_domain_tenant_domain"
        ),
        Index("ix_registry_email_domain_tenant", "tenant_id"),
    )


class RegistryTenantDbVersion(Base):
    """Each tenant DB's current Alembic revision (Phase 13.1.C, design §12).

    The control plane records where each tenant database sits in the ``tenant``
    migration chain so rollouts can be staged/canaried tenant-by-tenant and a
    bad migration's blast radius is one tenant.  One row per tenant.
    """

    __tablename__ = "registry_tenant_db_version"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        GUID(), ForeignKey("registry_tenant.id", ondelete="CASCADE"), nullable=False
    )
    # The Alembic chain this revision tracks ("tenant").  Stored explicitly so
    # the table can later track the shared chain too if needed.
    chain = Column(String(32), nullable=False, default="tenant")
    revision = Column(String(64), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "chain", name="uq_registry_db_version_tenant_chain"
        ),
        Index("ix_registry_db_version_tenant", "tenant_id"),
    )
