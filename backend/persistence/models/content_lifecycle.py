# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Content Lifecycle Management models (Phase 16).

Satellite-style Content Views + Lifecycle Environments + gated promotion, built
on the ``repository_mirroring_engine`` snapshot substrate.  Licensed logic lives
in the Enterprise ``content_lifecycle_engine``; the OSS build ships the schema +
an inert gate (402 when the engine isn't loaded).

Partition split (shared defs + tenant overlay — mirrors the advisory precedent):

* **shared partition** (``shared_*`` prefix, shared alembic chain) — platform
  truth, identical across tenants:
  - ``SharedLifecycleEnvironment`` — the ordered path (Library -> Dev -> ...).
  - ``SharedContentView`` — a named, filtered, versioned selection of mirrors.
  - ``SharedContentViewRepo`` — CV membership (intra-shared FK to the CV;
    ``mirror_id`` is a **soft** cross-partition ref to ``mirror_repository`` —
    NO ForeignKey; component CVs use ``component_content_view_id``).
  - ``SharedContentViewFilter`` — allow/deny/cutoff/security-only/by-date.
  - ``SharedContentViewVersion`` — the immutable, physically-materialized
    published version (``store_path`` on the mirror host).

* **tenant partition** (unprefixed, tenant alembic chain) — per-tenant promotion
  state.  All cross-partition references to the shared IDs are **soft** (no FK):
  - ``EnvironmentContentBinding`` — which CVV is promoted into which env.
  - ``ContentPromotionAudit`` — append-only publish/promote/rollback log.
  - ``EnvironmentSiteSubscription`` — a federation site subscribes to an env
    (orthogonal axes: env = content maturity, site = topology).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

# Content-view filter kinds (drive the publish-time materialize job).
FILTER_ALLOW = "allow"  # package allow-list
FILTER_DENY = "deny"  # package deny-list
FILTER_ADVISORY_CUTOFF = "advisory_cutoff"  # only advisories up to a date
FILTER_SECURITY_ONLY = "security_only"  # security-fix packages only
FILTER_BY_DATE = "by_date"  # packages published up to a date
FILTER_TYPES = (
    FILTER_ALLOW,
    FILTER_DENY,
    FILTER_ADVISORY_CUTOFF,
    FILTER_SECURITY_ONLY,
    FILTER_BY_DATE,
)

# Content-view-version lifecycle.
CVV_DRAFT = "draft"
CVV_PUBLISHING = "publishing"
CVV_PUBLISHED = "published"
CVV_FAILED = "failed"
CVV_DEPRECATED = "deprecated"
CVV_STATUSES = (CVV_DRAFT, CVV_PUBLISHING, CVV_PUBLISHED, CVV_FAILED, CVV_DEPRECATED)

# Promotion audit actions.
PROMOTION_PUBLISH = "publish"
PROMOTION_PROMOTE = "promote"
PROMOTION_ROLLBACK = "rollback"

# Retention: keep this many published versions per content view by default; the
# API caps operator overrides at this maximum (see the design doc §8).
DEFAULT_KEEP_VERSIONS = 5
MAX_KEEP_VERSIONS = 10


def _utcnow() -> datetime:
    """Naive-UTC now, matching the shared/tenant timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =============================================================================
# SHARED partition
# =============================================================================


class SharedLifecycleEnvironment(Base):
    """One stage on the ordered lifecycle path (Library -> Dev -> Test -> Prod)."""

    __tablename__ = "shared_lifecycle_environment"
    __table_args__ = (
        UniqueConstraint("name", name="uq_shared_lifecycle_env_name"),
        UniqueConstraint("position", name="uq_shared_lifecycle_env_position"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(120), nullable=False, index=True)
    # Ordered position along the path; promotion only moves forward one step.
    position = Column(Integer, nullable=False, default=0)
    # Exactly one environment is the Library (the publish target / path root).
    is_library = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "position": self.position,
            "is_library": bool(self.is_library),
            "description": self.description,
        }


class SharedContentView(Base):
    """A named, filtered, versioned selection of repository mirrors."""

    __tablename__ = "shared_content_view"
    __table_args__ = (UniqueConstraint("name", name="uq_shared_content_view_name"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    # A composite CV composes other CVs instead of referencing mirrors directly.
    composite = Column(Boolean, nullable=False, default=False)
    # Retention: keep this many published versions (default 5, API-capped at 10).
    keep_versions = Column(Integer, nullable=False, default=DEFAULT_KEEP_VERSIONS)
    created_by = Column(GUID(), nullable=True)  # soft ref to user
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    repos = relationship(
        "SharedContentViewRepo",
        back_populates="content_view",
        cascade="all, delete-orphan",
    )
    filters = relationship(
        "SharedContentViewFilter",
        back_populates="content_view",
        cascade="all, delete-orphan",
    )
    versions = relationship(
        "SharedContentViewVersion",
        back_populates="content_view",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "composite": bool(self.composite),
            "keep_versions": self.keep_versions,
        }


class SharedContentViewRepo(Base):
    """CV membership: a mirror (or, for a composite CV, a component CV)."""

    __tablename__ = "shared_content_view_repo"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    content_view_id = Column(
        GUID(),
        ForeignKey("shared_content_view.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Soft cross-partition ref to ``mirror_repository`` (tenant partition) — NO
    # ForeignKey; null for a composite-CV component row.
    mirror_id = Column(GUID(), nullable=True, index=True)
    # For composite CVs: an intra-shared ref to a component content view.
    component_content_view_id = Column(GUID(), nullable=True, index=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    content_view = relationship("SharedContentView", back_populates="repos")


class SharedContentViewFilter(Base):
    """A filter applied at publish time to select a subset of the content."""

    __tablename__ = "shared_content_view_filter"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    content_view_id = Column(
        GUID(),
        ForeignKey("shared_content_view.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filter_type = Column(String(30), nullable=False, index=True)  # FILTER_TYPES
    rule_json = Column(JSON, nullable=True)  # e.g. {"packages": [...]} / {"date": ...}
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    content_view = relationship("SharedContentView", back_populates="filters")


class SharedContentViewVersion(Base):
    """An immutable, physically-materialized published version of a content view."""

    __tablename__ = "shared_content_view_version"
    __table_args__ = (
        UniqueConstraint("content_view_id", "version", name="uq_shared_cvv_cv_version"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    content_view_id = Column(
        GUID(),
        ForeignKey("shared_content_view.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)  # monotonic per content view
    status = Column(String(20), nullable=False, default=CVV_DRAFT, index=True)
    # On-disk store on the mirror host (…/.content-views/{cv}/v{n}/…), immutable.
    store_path = Column(String(500), nullable=True)
    # Per-repo materialization record: {mirror_id, source_snapshot_id, file_count,
    # bytes, ...}; also carries the per-file sha256 manifest reference.
    manifest = Column(JSON, nullable=True)
    published_at = Column(DateTime, nullable=True)
    published_by = Column(GUID(), nullable=True)  # soft ref to user
    publish_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    content_view = relationship("SharedContentView", back_populates="versions")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "content_view_id": str(self.content_view_id),
            "version": self.version,
            "status": self.status,
            "store_path": self.store_path,
            "published_at": (
                self.published_at.isoformat() if self.published_at else None
            ),
        }


# =============================================================================
# TENANT partition (unprefixed; all shared refs are SOFT — no FK)
# =============================================================================


class EnvironmentContentBinding(Base):
    """Which content-view version is promoted into which environment (per tenant)."""

    __tablename__ = "environment_content_binding"
    __table_args__ = (
        UniqueConstraint(
            "environment_id", "content_view_id", name="uq_env_content_binding"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Soft cross-partition refs to shared IDs (no FK).
    environment_id = Column(GUID(), nullable=False, index=True)
    content_view_id = Column(GUID(), nullable=False, index=True)
    content_view_version_id = Column(GUID(), nullable=False, index=True)
    # The version bound before the current one — enables instant rollback.
    previous_version_id = Column(GUID(), nullable=True)
    promoted_at = Column(DateTime, nullable=False, default=_utcnow)
    promoted_by = Column(GUID(), nullable=True)  # soft ref to user
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "environment_id": str(self.environment_id),
            "content_view_id": str(self.content_view_id),
            "content_view_version_id": str(self.content_view_version_id),
            "previous_version_id": (
                str(self.previous_version_id) if self.previous_version_id else None
            ),
        }


class ContentPromotionAudit(Base):
    """Append-only audit of publish / promote / rollback actions."""

    __tablename__ = "content_promotion_audit"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    content_view_id = Column(GUID(), nullable=False, index=True)  # soft ref
    from_environment_id = Column(GUID(), nullable=True)  # soft ref
    to_environment_id = Column(GUID(), nullable=True)  # soft ref
    content_view_version_id = Column(GUID(), nullable=False)  # soft ref
    action = Column(String(20), nullable=False, index=True)  # publish/promote/rollback
    actor = Column(GUID(), nullable=True)  # soft ref to user
    note = Column(Text, nullable=True)
    at = Column(DateTime, nullable=False, default=_utcnow, index=True)


class EnvironmentSiteSubscription(Base):
    """A federation site subscribes to an environment (orthogonal to topology)."""

    __tablename__ = "environment_site_subscription"
    __table_args__ = (
        UniqueConstraint("environment_id", "site_id", name="uq_env_site_subscription"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    environment_id = Column(GUID(), nullable=False, index=True)  # soft ref
    site_id = Column(GUID(), nullable=False, index=True)  # soft ref
    created_at = Column(DateTime, nullable=False, default=_utcnow)
