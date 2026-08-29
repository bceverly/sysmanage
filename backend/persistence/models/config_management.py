# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Configuration-management profile storage (Phase 20.1).

Its own module rather than another entry in ``proplus.py`` for the same reason
content_lifecycle and repository_mirroring have theirs: one file per feature
keeps each readable, and proplus.py had already reached the 1000-line ceiling.

The SCHEMA is here, in the open-source tree, because the OSS server owns the
database. The BEHAVIOUR -- validating a profile, versioning it, resolving an
assignment, deciding when a schedule is due -- lives in the Pro+
``config_management_engine``. That is the same split Vulnerability and
ComplianceProfile use.
"""

import uuid

from sqlalchemy import (
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
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"
CASCADE_DELETE = "CASCADE"
# Referenced by versions, assignments and drift findings.
PROFILE_ID_FK = "config_profile.id"
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"


class ConfigProfile(Base):
    """A named, reusable configuration profile (Phase 20.1).

    WHY THE SCHEMA IS HERE AND THE LOGIC IS NOT
    -------------------------------------------
    Profile AUTHORING is a Pro+ capability, but the OSS server owns the
    database -- the same split every other engine uses (Vulnerability and
    ComplianceProfile live in this file too, driven by their engines). Putting
    the table here means an unlicensed install still has a coherent schema and
    its existing run history keeps its foreign key.

    ``engine`` names one of the identities in config_mgmt_engines; it decides
    how ``content`` is interpreted. Storing it per profile rather than per host
    is the whole point of the per-engine refactor: a profile IS a Puppet
    manifest or a Salt state, and the host it runs on does not change that.
    """

    __tablename__ = "config_profile"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    engine = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    # Bumped on every content change; the previous body is snapshotted into
    # config_profile_version. Mirrors how SavedScript versions work, so an
    # operator sees one convention across scripts and profiles.
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    versions = relationship(
        "ConfigProfileVersion",
        back_populates="profile",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
        passive_deletes=True,
    )
    assignments = relationship(
        "ConfigProfileAssignment",
        back_populates="profile",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<ConfigProfile(id={self.id}, name='{self.name}', "
            f"engine='{self.engine}', version={self.version})>"
        )


class ConfigProfileVersion(Base):
    """A prior body of a profile, kept so a change can be seen and undone.

    Config-as-code without history is just config: the value of a stored
    profile is being able to answer "what changed, and when" after a run starts
    behaving differently. Retrofitting this later would mean the versions
    before the retrofit are gone for good, which is why it lands with the
    table rather than after it.
    """

    __tablename__ = "config_profile_version"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey(PROFILE_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    engine = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)

    profile = relationship("ConfigProfile", back_populates="versions")

    __table_args__ = (
        # One row per (profile, version): a duplicate would make "restore
        # version 3" ambiguous.
        Index(
            "ix_config_profile_version_unique",
            "profile_id",
            "version",
            unique=True,
        ),
    )


class ConfigProfileAssignment(Base):
    """Where a profile applies: one host, one tag, or one site.

    Exactly one target column is set. Three nullable columns rather than a
    (target_type, target_id) pair because that pair cannot be a foreign key --
    it would let an assignment outlive the host it names, and the first symptom
    would be a scheduled run against a machine that no longer exists.

    ``schedule`` is a cron expression, or NULL for "assigned but only applied
    on request". Enforcement belongs to the Pro+ engine; this table only
    records intent.
    """

    __tablename__ = "config_profile_assignment"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        GUID(),
        ForeignKey(PROFILE_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    host_id = Column(
        GUID(), ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE), nullable=True
    )
    tag_id = Column(
        GUID(), ForeignKey("tags.id", ondelete=CASCADE_DELETE), nullable=True
    )
    site_id = Column(
        GUID(),
        ForeignKey("federation_sites.id", ondelete=CASCADE_DELETE),
        nullable=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    schedule = Column(String(100), nullable=True)
    # A scheduled assignment that only ever reports drift, never fixes it.
    check_mode = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    last_applied_at = Column(DateTime, nullable=True)

    profile = relationship("ConfigProfile", back_populates="assignments")

    __table_args__ = (
        # The scheduler's query is "enabled assignments, by target"; without
        # this it scans every assignment on every tick.
        Index("ix_config_profile_assignment_enabled", "enabled", "profile_id"),
    )

    def __repr__(self):
        target = self.host_id or self.tag_id or self.site_id
        return (
            f"<ConfigProfileAssignment(id={self.id}, "
            f"profile_id={self.profile_id}, target={target})>"
        )


class ConfigDriftFinding(Base):
    """One divergence between a host and a profile, and how long it has lasted.

    WHY THIS EXISTS AT ALL, GIVEN ``config_profile_run``
    ----------------------------------------------------
    A check-mode run already says WHAT would change. What it cannot say is
    SINCE WHEN -- each run only knows about itself, so "this host has been
    drifting for nine days" is unanswerable from run rows without scanning the
    whole history on every page load. This table is exactly that lifespan and
    nothing else: the runs stay the record of what happened.

    WHAT IDENTIFIES "THE SAME" DRIFT ACROSS RUNS
    --------------------------------------------
    ``(host_id, profile_id, task_name)``. That is the only identity the generic
    result shape carries -- the agent reports a task NAME, and nothing more
    stable travels with it.

    The accepted cost: renaming a task in a profile starts its drift age over,
    because the new name is a different row. That is the right trade rather
    than matching on task ORDER, which would silently re-attribute one task's
    history to another the moment somebody inserted a step -- a wrong date is
    worse than a reset one, because a reset is visibly a reset.
    """

    __tablename__ = "config_drift_finding"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(), ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE), nullable=False
    )
    # Softened deliberately: a finding outlives the profile being deleted only
    # long enough to be cleaned up, and a hard FK would take drift history with
    # it. Mirrors config_profile_run.profile_id.
    profile_id = Column(
        GUID(),
        ForeignKey(PROFILE_ID_FK, ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_name = Column(String(255), nullable=True)
    task_name = Column(String(500), nullable=False)
    # The agent's own message for this task, when it gave one -- "would change
    # permissions 0644 -> 0600" is the difference between a finding an operator
    # can act on and a task name they have to go and read the profile for.
    detail = Column(Text, nullable=True)

    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    # NULL means still drifting. Set when a later SUCCESSFUL check-mode run of
    # the same profile stops reporting this task as changed.
    resolved_at = Column(DateTime, nullable=True)
    # The run that most recently observed it, so the dashboard can link back to
    # the full task detail rather than duplicating it here.
    last_run_id = Column(GUID(), nullable=True)

    __table_args__ = (
        # The identity above, enforced. Without it a race between two ticks
        # would open two rows for the same divergence and the age column would
        # depend on which one the page happened to read.
        UniqueConstraint(
            "host_id",
            "profile_id",
            "task_name",
            name="uq_config_drift_finding_identity",
        ),
        # The dashboard's query is "open findings, newest first".
        Index("ix_config_drift_finding_open", "resolved_at", "last_seen_at"),
        Index("ix_config_drift_finding_host", "host_id", "resolved_at"),
    )

    def __repr__(self):
        state = "resolved" if self.resolved_at else "open"
        return (
            f"<ConfigDriftFinding(host_id={self.host_id}, "
            f"task={self.task_name!r}, {state})>"
        )
