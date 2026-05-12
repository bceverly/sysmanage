"""
Air-gap models (Phase 11).

Three tables shared by the OSS routes and both Pro+ engines:

  ``AirgapCollectionRun``        — collector-side: one row per run
  ``AirgapCollectionTarget``     — collector-side: per-distro target
  ``AirgapMediaManifest``        — collector-side: produced ISO + sig

The ingestion side adds its own tables in a separate model file
(``airgap_repository.py``) keyed off the manifest's signer fingerprint
plus the collection_run reference; we don't FK across servers because
the two halves never share a database.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
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

# Constants extracted to satisfy SonarQube duplicate-literal rules.
_FK_COLLECTION_RUN = "airgap_collection_run.id"
_ON_DELETE_SET_NULL = "SET NULL"
_ON_DELETE_CASCADE = "CASCADE"


class AirgapCollectionRun(Base):
    """One row per air-gap collection job."""

    __tablename__ = "airgap_collection_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    iso_label = Column(String(80), nullable=False)
    media_size_bytes = Column(BigInteger, nullable=False, default=4_700_000_000)
    include_cve = Column(Boolean, nullable=False, default=True)
    include_compliance = Column(Boolean, nullable=False, default=True)

    # Lifecycle: QUEUED -> MIRRORING -> STAGING_COMPLETE -> ISO_BUILT
    #          -> BURNING -> COMPLETE | FAILED
    status = Column(String(40), nullable=False, default="QUEUED")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_by = Column(
        GUID(),
        ForeignKey(
            "user.id",
            name="fk_airgap_collection_run_created_by",
            ondelete=_ON_DELETE_SET_NULL,
        ),
        nullable=True,
    )

    # Phase 11 B3 — delta collection.  When this run is a delta of a
    # prior run, ``parent_run_id`` points at it; the engine reads the
    # parent's manifest files to compute a skip-set.  NULL = full
    # snapshot (the v0.1.0 default).
    parent_run_id = Column(
        GUID(),
        ForeignKey(
            _FK_COLLECTION_RUN,
            name="fk_airgap_collection_run_parent_run_id",
            ondelete=_ON_DELETE_SET_NULL,
        ),
        nullable=True,
    )

    # Phase 11.1 follow-up — cron-driven scheduling.  When set, the
    # server-side scheduler tick (POST
    # ``/airgap/collector/collection/runs/tick``) re-fires this run
    # from ``SCHEDULED`` to ``QUEUED`` on each cron match.  NULL means
    # the run is one-shot / on-demand (the v0.1.0 default).
    cron_schedule = Column(String(200), nullable=True)

    targets = relationship(
        "AirgapCollectionTarget",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    manifests = relationship(
        "AirgapMediaManifest",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "iso_label",
            "created_at",
            name="uq_airgap_collection_run_label_time",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "iso_label": self.iso_label,
            "media_size_bytes": self.media_size_bytes,
            "include_cve": self.include_cve,
            "include_compliance": self.include_compliance,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "cron_schedule": self.cron_schedule,
            "parent_run_id": (str(self.parent_run_id) if self.parent_run_id else None),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AirgapCollectionTarget(Base):
    """A single distro/version target inside a collection run."""

    __tablename__ = "airgap_collection_target"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        GUID(),
        ForeignKey(
            _FK_COLLECTION_RUN,
            name="fk_airgap_collection_target_run_id",
            ondelete=_ON_DELETE_CASCADE,
        ),
        nullable=False,
    )
    distro = Column(String(40), nullable=False)
    version = Column(String(40), nullable=False)
    repos = Column(Text, nullable=True)  # comma-separated repo names
    byte_count = Column(BigInteger, nullable=True)
    file_count = Column(Integer, nullable=True)
    status = Column(String(40), nullable=True)

    run = relationship("AirgapCollectionRun", back_populates="targets")


class AirgapMediaManifest(Base):
    """Produced ISO + signed manifest envelope for one disc.

    Disc-level row so multi-disc spanning (Phase 11.1 follow-up) can
    coexist with the single-disc happy path: ``disc_index = 1`` and
    ``disc_count = 1`` for v0.1.0.
    """

    __tablename__ = "airgap_media_manifest"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        GUID(),
        ForeignKey(
            _FK_COLLECTION_RUN,
            name="fk_airgap_media_manifest_run_id",
            ondelete=_ON_DELETE_CASCADE,
        ),
        nullable=False,
    )
    disc_index = Column(Integer, nullable=False, default=1)
    disc_count = Column(Integer, nullable=False, default=1)
    iso_path = Column(String(500), nullable=False)
    iso_sha256 = Column(String(64), nullable=False)
    iso_size_bytes = Column(BigInteger, nullable=False)
    manifest_json = Column(Text, nullable=False)
    signature = Column(Text, nullable=False)
    signer_fingerprint = Column(String(128), nullable=False)
    signature_algorithm = Column(String(40), nullable=False, default="ed25519")
    format_version = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    run = relationship("AirgapCollectionRun", back_populates="manifests")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "disc_index",
            name="uq_airgap_media_manifest_run_disc",
        ),
    )


class AirgapIngestionRun(Base):
    """Repository-side ingestion run.  No FK back to the collection
    run because the two halves never share a database — instead we
    record the signer fingerprint + collector_id from the verified
    manifest so audit trails can correlate across the air gap by
    inspecting both halves' DBs after the fact."""

    __tablename__ = "airgap_ingestion_run"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    iso_path = Column(String(500), nullable=False)
    iso_sha256 = Column(String(64), nullable=True)

    # Pulled from the verified manifest envelope, NOT from a FK — the
    # two air-gap halves never share a database.
    signer_fingerprint = Column(String(128), nullable=True)
    manifest_format_version = Column(Integer, nullable=True)
    collector_iso_label = Column(String(80), nullable=True)
    captured_at = Column(DateTime, nullable=True)

    # Lifecycle: QUEUED -> VERIFYING_SIG -> VERIFYING_HASHES
    #          -> COPYING -> METADATA_GEN -> COMPLETE | FAILED
    status = Column(String(40), nullable=False, default="QUEUED")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    file_count = Column(Integer, nullable=True)
    byte_count = Column(BigInteger, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_by = Column(
        GUID(),
        ForeignKey(
            "user.id",
            name="fk_airgap_ingestion_run_created_by",
            ondelete=_ON_DELETE_SET_NULL,
        ),
        nullable=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "iso_path": self.iso_path,
            "iso_sha256": self.iso_sha256,
            "signer_fingerprint": self.signer_fingerprint,
            "collector_iso_label": self.collector_iso_label,
            "captured_at": (self.captured_at.isoformat() if self.captured_at else None),
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "error_message": self.error_message,
            "file_count": self.file_count,
            "byte_count": self.byte_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AirgapCollectionSchedule(Base):
    """Cron-driven schedule for recurring air-gap collection runs.

    On each tick, the OSS route iterates due schedules and posts to
    the same engine.build_collection_run_plan path that on-demand
    runs use.  The cron parser comes from automation_engine (which
    must also be licensed; both are Enterprise tier) — keeps us out
    of having a third copy of the cron parser.
    """

    __tablename__ = "airgap_collection_schedule"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False, unique=True)
    cron = Column(String(200), nullable=False, default="0 3 * * *")
    enabled = Column(Boolean, nullable=False, default=True)

    # Frozen request body used as the input to build_collection_run_plan
    # on each tick.  Stored as JSON text — engine validates the shape
    # at run time, so cron schedules captured today still work after
    # an engine upgrade that adds new optional request fields.
    target_request_json = Column(Text, nullable=False)

    last_run = Column(DateTime, nullable=True)
    last_status = Column(String(40), nullable=True)
    last_run_id = Column(
        GUID(),
        ForeignKey(
            _FK_COLLECTION_RUN,
            name="fk_airgap_collection_schedule_last_run_id",
            ondelete=_ON_DELETE_SET_NULL,
        ),
        nullable=True,
    )
    next_run = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "cron": self.cron,
            "enabled": self.enabled,
            "target_request_json": self.target_request_json,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_status": self.last_status,
            "last_run_id": str(self.last_run_id) if self.last_run_id else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }


class AirgapLocalRepository(Base):
    """A locally-served package repository materialized from one or
    more ingestion runs.  ``last_ingest_run_id`` lets compliance
    context resolve "how stale is this distro's mirror" without
    re-scanning the filesystem."""

    __tablename__ = "airgap_local_repository"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    distro = Column(String(40), nullable=False)
    version = Column(String(40), nullable=False)
    repo_url = Column(String(500), nullable=False)
    last_ingest_run_id = Column(
        GUID(),
        ForeignKey(
            "airgap_ingestion_run.id",
            name="fk_airgap_local_repository_last_ingest",
            ondelete=_ON_DELETE_SET_NULL,
        ),
        nullable=True,
    )
    last_ingest_at = Column(DateTime, nullable=True)
    package_count = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "distro",
            "version",
            name="uq_airgap_local_repository_distro_version",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "distro": self.distro,
            "version": self.version,
            "repo_url": self.repo_url,
            "last_ingest_at": (
                self.last_ingest_at.isoformat() if self.last_ingest_at else None
            ),
            "package_count": self.package_count,
        }
