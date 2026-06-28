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
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# FK target for the registry tenant primary key — referenced by every
# tenant-scoped registry table (grant/placement/email-domain/etc.).
_TENANT_FK = "registry_tenant.id"

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
TENANT_STATUS_DEPROVISIONING = "deprovisioning"
TENANT_STATUSES = (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
    TENANT_STATUS_PROVISIONING,
    TENANT_STATUS_DEPROVISIONING,
)

# Phase 13.1.J — per-tenant edition. Each tenant is independently assigned a
# feature surface from the control plane; module/feature gating resolves against
# the TENANT's edition (via the active-tenant context), not one global license
# tier. The resolution + Platform-Operator authorization logic lives in the
# licensed ``multitenancy_engine`` (the moat); only these columns/constants are
# OSS. Default ``enterprise`` so existing SaaS tenants are unchanged on upgrade.
TENANT_EDITION_COMMUNITY = "community"
TENANT_EDITION_PROFESSIONAL = "professional"
TENANT_EDITION_ENTERPRISE = "enterprise"
TENANT_EDITIONS = (
    TENANT_EDITION_COMMUNITY,
    TENANT_EDITION_PROFESSIONAL,
    TENANT_EDITION_ENTERPRISE,
)

# Phase 13.1.F — per-tenant backup/RPO orchestration. SysManage tracks each
# tenant's backup schedule (RPO) and verification status; the actual bytes are
# produced by an operator-configured external command (orchestrate-only). The
# orchestration logic lives in the licensed ``multitenancy_engine``; only this
# run-history table + constants are OSS.
BACKUP_KIND_BACKUP = "backup"
BACKUP_KIND_VERIFY = "verify"
BACKUP_KINDS = (BACKUP_KIND_BACKUP, BACKUP_KIND_VERIFY)

# A verify run is either a cheap dump-integrity check (after every backup) or a
# scheduled full restore into a scratch database.
BACKUP_VERIFY_INTEGRITY = "integrity"
BACKUP_VERIFY_FULL = "full"
BACKUP_VERIFY_KINDS = (BACKUP_VERIFY_INTEGRITY, BACKUP_VERIFY_FULL)

BACKUP_STATUS_RUNNING = "running"
BACKUP_STATUS_SUCCESS = "success"
BACKUP_STATUS_FAILED = "failed"
BACKUP_STATUSES = (
    BACKUP_STATUS_RUNNING,
    BACKUP_STATUS_SUCCESS,
    BACKUP_STATUS_FAILED,
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
    # Per-tenant feature surface (Phase 13.1.J). Defaults to enterprise so tenants
    # created before this column behave exactly as before. Resolution logic is in
    # the licensed multitenancy_engine; this column is the OSS source of truth.
    edition = Column(
        String(32),
        nullable=False,
        default=TENANT_EDITION_ENTERPRISE,
        server_default=TENANT_EDITION_ENTERPRISE,
    )
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
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
    )
    role = Column(String(64), nullable=False, default="member")
    is_default = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=True)
    # Phase 13.1.E: accessor of the OpenBAO token whose lease mirrors a
    # vendor-support / break-glass grant window.  NULL unless OpenBAO is enabled
    # and a support lease was minted; lets revoke_support_grant kill the live
    # vault lease in addition to expiring the grant.
    support_lease_accessor = Column(String(255), nullable=True)
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
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
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
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
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
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
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


class RegistryTenantBackup(Base):
    """One per-tenant backup or restore-verification *run* (Phase 13.1.F).

    The control plane records every backup attempt and every verification so it
    can report RPO compliance ("how long since the last good backup?") and prove
    restorability.  SysManage orchestrates the schedule and runs an
    operator-configured external command (pgBackRest/wal-g/pg_dump); it does not
    itself store the backup bytes — ``artifact_ref`` is whatever opaque handle
    that command reports (a stanza label, object key, file path).

    ``kind`` distinguishes a backup run from a verify run; for verify runs,
    ``verify_kind`` is the cheap ``integrity`` check (run after each backup) or
    the scheduled ``full`` scratch-restore.  ``rpo_seconds`` snapshots the
    tenant's target at run time so history stays meaningful if the target later
    changes.
    """

    __tablename__ = "registry_tenant_backup"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
    )
    kind = Column(String(16), nullable=False, default=BACKUP_KIND_BACKUP)
    # Only set for kind == "verify": "integrity" | "full".
    verify_kind = Column(String(16), nullable=True)
    status = Column(String(16), nullable=False, default=BACKUP_STATUS_RUNNING)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)
    # The tenant's RPO target (seconds) at the time of this run, for history.
    rpo_seconds = Column(Integer, nullable=True)
    # Opaque handle the external backup tool reports (stanza/object key/path).
    artifact_ref = Column(String(1024), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    # Captured stderr / failure reason when status == "failed".
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_registry_tenant_backup_tenant", "tenant_id"),
        Index(
            "ix_registry_tenant_backup_tenant_started",
            "tenant_id",
            "started_at",
        ),
    )


class RegistryEnrollmentToken(Base):
    """A tenant-scoped agent enrollment token (Phase 13.1 data plane).

    An admin generates a token bound to a tenant; an agent presents it at
    registration to be enrolled into that tenant (its host record is then
    created in the tenant's database).  Only the SHA-256 ``token_hash`` is
    stored — the plaintext is shown once at creation and never persisted.

    Optional ``expires_at`` and ``max_uses`` bound a token's blast radius;
    ``revoked`` disables it immediately.  ``use_count`` / ``last_used_at`` are
    bumped on each successful enrollment for audit.
    """

    __tablename__ = "registry_enrollment_token"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex of the plaintext token — looked up at enrollment.  Unique so
    # a token maps to exactly one tenant.
    token_hash = Column(String(64), nullable=False, unique=True)
    label = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    max_uses = Column(Integer, nullable=True)  # unlimited uses when NULL
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_registry_enrollment_token_tenant", "tenant_id"),
        Index("ix_registry_enrollment_token_hash", "token_hash"),
    )


class RegistryHostTenant(Base):
    """Server-global host→tenant index (Phase 13.1 data plane).

    A host's data lives in its tenant's database, but the websocket / queue
    processors only know a host by its id (or token) — they can't query the
    per-tenant DBs to discover *which* tenant owns a host without first knowing
    the tenant (chicken-and-egg).  This registry-level index resolves that:
    populated at enrollment, read by the data plane to route a host's
    operations to the right tenant database.

    One row per host (``host_id`` unique).  ``host_id`` is a soft reference to
    the host row (which lives in the tenant DB) — no cross-partition FK.
    """

    __tablename__ = "registry_host_tenant"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=False, unique=True)
    tenant_id = Column(
        GUID(), ForeignKey(_TENANT_FK, ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_registry_host_tenant_host", "host_id"),
        Index("ix_registry_host_tenant_tenant", "tenant_id"),
    )
