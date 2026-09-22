# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Watched-file state and the lists that drive it (ROADMAP 21.1 S7).

S7 extends the 20.2 golden-host differ to arbitrary file and config state. The
20.2 half compares inventory the server already holds -- packages, users,
mounts. This half compares files, which nothing collected before, so it needs
both a policy layer (which paths to watch, on which hosts) and a storage layer
(what each host reported).

WHAT IS STORED, AND WHAT IS DELIBERATELY NOT
---------------------------------------------
A sha256 and stat metadata per watched path. **Never file contents** -- see the
agent's ``collection/fact_file_state.py`` for the full argument. The short
version: hashes let an operator watch ``/etc/shadow`` or a private key without
those bytes entering this database, its API responses, its backups or its
logs. Drift therefore reports THAT a file changed, not WHAT changed in it.

PARTITION SPLIT -- the same rule as query packs and advisories
---------------------------------------------------------------
A curated watch list ("CIS Linux baseline config") is identical for every
customer, so the catalog lives ONCE in the ``shared`` partition. What is
per-customer is which hosts watch it.

* **shared partition** -- ``SharedFileWatch`` / ``SharedFileWatchPath``
* **tenant partition** -- ``FileWatch`` / ``FileWatchPath`` (customer-authored),
  ``FileWatchAssignment`` (policy), ``HostFileState`` (what came back)

``FileWatchAssignment.shared_watch_id`` is a SOFT reference with no ForeignKey,
for the reason ``QueryPackAssignment`` documents: under scale-out the shared
catalog is a different database and the constraint could not be enforced there.

WHY EVERY WATCHED PATH GETS A ROW, INCLUDING THE ABSENT ONES
--------------------------------------------------------------
``HostFileState`` stores one row per watched path per host whatever happened to
it -- ``present``, ``absent``, ``unreadable``, ``not_a_file``, ``too_large``.
Storing only the files that exist would make a DELETED config file
indistinguishable from one nobody watched, and the differ would then silently
not report the deletion. That is the phase's central property applied to files:
not measured must never look like measured and unchanged.
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
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"
CASCADE_DELETE = "CASCADE"
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
WATCH_ID_FK = "file_watch.id"
SHARED_WATCH_ID_FK = "shared_file_watch.id"

DEFAULT_INTERVAL_MINUTES = 60
# Floor on how often a watch list may be collected. Hashing a fleet's config
# every minute is a self-inflicted outage, and the tick's own cadence is 60s
# anyway. Defined HERE, beside the default, so the API that refuses an
# operator's value and the tick that clamps it cannot drift apart.
MIN_INTERVAL_MINUTES = 5

# The agent's own vocabulary, mirrored here so a server-side consumer does not
# have to import from the agent or, worse, hardcode the strings inline. Kept
# in step with collection/fact_file_state.py.
STATE_PRESENT = "present"
STATE_ABSENT = "absent"
STATE_UNREADABLE = "unreadable"
STATE_NOT_A_FILE = "not_a_file"
STATE_TOO_LARGE = "too_large"

# States in which the host did NOT manage to measure the path. A difference
# between two hosts where either side is in one of these is a BLIND SPOT, not
# drift -- reporting it as drift invents a divergence, and hiding it entirely
# claims a comparison that never happened.
STATES_NOT_MEASURED = (STATE_UNREADABLE, STATE_TOO_LARGE)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# shared partition -- the curated catalog
# ---------------------------------------------------------------------------


class SharedFileWatch(Base):
    """A curated watch list. Global reference data, never per tenant."""

    __tablename__ = "shared_file_watch"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_shared_file_watch_slug"),
        Index("ix_shared_file_watch_enabled", "deprecated"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Stable identity across catalog refreshes -- an assignment survives on the
    # slug, not the locally minted uuid.
    slug = Column(String(128), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    category = Column(String(64), nullable=True, index=True)
    deprecated = Column(Boolean, nullable=False, default=False)
    source = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    paths = relationship(
        "SharedFileWatchPath",
        back_populates="watch",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<SharedFileWatch(slug={self.slug}, version={self.version})>"


class SharedFileWatchPath(Base):
    """One path inside a curated watch list."""

    __tablename__ = "shared_file_watch_path"
    __table_args__ = (
        UniqueConstraint("shared_watch_id", "path", name="uq_shared_file_watch_path"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    shared_watch_id = Column(
        GUID(),
        ForeignKey(SHARED_WATCH_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    path = Column(String(1024), nullable=False)
    description = Column(Text, nullable=True)
    # Which platforms this path exists on. A list naming /etc/ssh/sshd_config
    # should not make a Windows host report it absent -- absent means "it
    # should be here and is not", which is drift, and that would be a
    # fabricated one.
    platforms = Column(JSON, nullable=True)

    watch = relationship("SharedFileWatch", back_populates="paths")

    def __repr__(self):
        return f"<SharedFileWatchPath(path={self.path})>"


# ---------------------------------------------------------------------------
# tenant partition -- what a customer wrote, assigned, and got back
# ---------------------------------------------------------------------------


class FileWatch(Base):
    """A watch list a customer wrote. Tenant data, never shared."""

    __tablename__ = "file_watch"
    __table_args__ = (UniqueConstraint("name", name="uq_file_watch_name"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    paths = relationship(
        "FileWatchPath", back_populates="watch", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    assignments = relationship(
        "FileWatchAssignment", back_populates="watch", cascade=CASCADE_ALL_DELETE_ORPHAN
    )

    def __repr__(self):
        return f"<FileWatch(name={self.name})>"


class FileWatchPath(Base):
    """One path inside a tenant-authored watch list."""

    __tablename__ = "file_watch_path"
    __table_args__ = (UniqueConstraint("watch_id", "path", name="uq_file_watch_path"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    watch_id = Column(
        GUID(),
        ForeignKey(WATCH_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    path = Column(String(1024), nullable=False)
    description = Column(Text, nullable=True)
    platforms = Column(JSON, nullable=True)

    watch = relationship("FileWatch", back_populates="paths")

    def __repr__(self):
        return f"<FileWatchPath(path={self.path})>"


class FileWatchAssignment(Base):
    """Which hosts watch which list -- the multi-tenant policy itself.

    Exactly one of ``watch_id`` (tenant-authored) and ``shared_watch_id``
    (curated) is set. ``shared_watch_id`` has NO ForeignKey on purpose: it
    crosses a partition boundary. Same shape, and the same reasoning, as
    ``QueryPackAssignment``.
    """

    __tablename__ = "file_watch_assignment"
    __table_args__ = (
        Index("ix_file_watch_assignment_enabled", "enabled", "watch_id"),
        Index("ix_file_watch_assignment_shared", "enabled", "shared_watch_id"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    watch_id = Column(
        GUID(), ForeignKey(WATCH_ID_FK, ondelete=CASCADE_DELETE), nullable=True
    )
    # SOFT reference to shared_file_watch.id -- see the class docstring.
    shared_watch_id = Column(GUID(), nullable=True, index=True)
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
    interval_minutes = Column(Integer, nullable=False, default=DEFAULT_INTERVAL_MINUTES)
    last_watch_version = Column(Integer, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    last_dispatched_at = Column(DateTime, nullable=True)

    watch = relationship("FileWatch", back_populates="assignments")

    def __repr__(self):
        target = self.host_id or self.tag_id or self.site_id
        return f"<FileWatchAssignment(id={self.id}, target={target})>"


class HostFileState(Base):
    """What one host reported for one watched path.

    One row per (host, path), replaced on each collection. The row exists
    whatever the outcome -- including ``absent`` -- because storing only the
    files that exist would make a deleted config indistinguishable from an
    unwatched one, and the differ would then miss the deletion entirely.
    """

    __tablename__ = "host_file_state"
    __table_args__ = (
        UniqueConstraint("host_id", "path", name="uq_host_file_state_path"),
        # The differ's query is "every watched path for this host".
        Index("ix_host_file_state_host", "host_id", "path"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    path = Column(String(1024), nullable=False)
    # present | absent | unreadable | not_a_file | too_large -- never NULL.
    # A null state would reintroduce exactly the ambiguity the column exists
    # to remove.
    state = Column(String(32), nullable=False)
    sha256 = Column(String(64), nullable=True)
    size = Column(Integer, nullable=True)
    mode = Column(String(8), nullable=True)
    uid = Column(Integer, nullable=True)
    gid = Column(Integer, nullable=True)
    owner = Column(String(255), nullable=True)
    group_name = Column(String(255), nullable=True)
    mtime = Column(Integer, nullable=True)
    type = Column(String(16), nullable=True)
    target = Column(String(1024), nullable=True)
    collected_at = Column(DateTime, nullable=False, default=_utcnow)

    def __repr__(self):
        return f"<HostFileState(path={self.path}, state={self.state})>"
