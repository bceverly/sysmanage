# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Query packs over the Phase 21.1 fact substrate (ROADMAP 21.1 S4 + S5).

A pack is a named, versioned set of SQL queries run against the osquery-schema
fact tables the agent serves (see the agent's ``core/fact_schema.py``).  S1-S3
built the substrate; this is the management plane over it.

PARTITION SPLIT -- the part to get right
----------------------------------------
Curated packs are **global reference data**: "listening ports on non-standard
interfaces" is the same query for every customer, so the catalog lives ONCE in
the ``shared`` partition, exactly like ``shared_advisory`` and
``shared_vulnerability``.  What is per-customer is which hosts run it.

* **shared partition** (``shared_*``, shared alembic chain)
  - ``SharedQueryPack`` -- a curated pack, versioned and offline-updatable.
  - ``SharedQueryPackQuery`` -- its queries (intra-shared FK: real FK is fine).

* **tenant partition** (unprefixed, tenant alembic chain)
  - ``QueryPack`` / ``QueryPackQuery`` -- packs a customer wrote themselves.
  - ``QueryPackAssignment`` -- which hosts/tags/sites run which pack.
  - ``QueryPackRun`` / ``QueryPackResultRow`` -- what came back.
  - ``QueryPackLiveQuery`` (S5) -- one ad-hoc statement fanned out across a
    fleet, bounded. Its targets ARE ``QueryPackRun`` rows, which is what lets
    the agent command and the result-correlation path stay exactly as S4 left
    them.

"Distributed as multi-tenant policy" means ONE shared catalog plus per-tenant
assignment -- never per-tenant copies of the curated packs.

WHY AN ASSIGNMENT POINTS AT EITHER OF TWO TABLES
------------------------------------------------
A pack is curated (shared) or tenant-authored, and an assignment must be able
to target both.  It therefore carries ``shared_pack_id`` OR ``pack_id``,
exactly one of them.  ``shared_pack_id`` is a **soft** reference with no
ForeignKey: under scale-out the shared catalog is a different database, and a
cross-partition FK cannot be enforced there -- the same rule
``host_vulnerability_finding`` and ``host_applicable_advisory`` follow.

The cost is real and worth stating: nothing at the database level stops an
assignment outliving the shared pack it names.  That is why resolution is
explicit about a missing pack rather than treating it as "no queries" -- a
silently empty pack would report a host as clean when it was never asked.

WHY RESULTS ARE ROWS AND NOT A JSON BLOB
-----------------------------------------
``QueryPackResultRow`` stores one row per result row, with the query's own
columns as JSON.  A blob per run would be smaller, but every consumer in S6 --
compliance, vuln, drift -- wants "which hosts returned a row matching X", and
that is a query over rows, not a scan of documents.

NOT MEASURED IS NOT EMPTY
-------------------------
The substrate's central property survives up here.  A run carries a STATUS and
each result carries the table coverage it ran against, so "this host returned
no rows" and "this host could not serve the tables the query needs" stay
distinguishable all the way to the UI.  Collapsing them would make a host that
cannot answer look compliant.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
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
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
PACK_ID_FK = "query_pack.id"
SHARED_PACK_ID_FK = "shared_query_pack.id"
RUN_ID_FK = "query_pack_run.id"

# How often a pack wants to run.  Minutes, not cron: the agent tick is the
# pacing mechanism (see ``query_pack_tick``), and a cron grammar would promise
# a precision the tick cannot deliver.
DEFAULT_INTERVAL_MINUTES = 60
MIN_INTERVAL_MINUTES = 5

# Run outcomes.  ``partial`` is the one that earns its place: the pack ran, some
# queries answered and others could not because the host does not serve their
# tables.  Without it those hosts would read as ``success`` with fewer rows --
# which is precisely the "measured and empty" confusion the substrate exists to
# prevent.
#
# A live-query target that has been created but NOT yet released into a wave
# (S5). Distinct from ``pending``, which means "dispatched, awaiting the
# agent's answer" -- collapsing the two would make an unbounded fan-out
# indistinguishable from a bounded one that has not finished yet, which is the
# exact property S5 exists to provide.
RUN_STATUS_WAITING = "waiting"
RUN_STATUS_PENDING = "pending"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_PARTIAL = "partial"
RUN_STATUS_FAILED = "failed"
RUN_STATUSES = (
    RUN_STATUS_WAITING,
    RUN_STATUS_PENDING,
    RUN_STATUS_SUCCESS,
    RUN_STATUS_PARTIAL,
    RUN_STATUS_FAILED,
)

# Why a single query produced nothing.  Same discipline as the fact contract's
# reason codes: a code the UI renders, not a sentence the server composed.
QUERY_STATUS_OK = "ok"
QUERY_STATUS_NOT_COVERED = "not_covered"
QUERY_STATUS_ERROR = "error"
QUERY_STATUSES = (QUERY_STATUS_OK, QUERY_STATUS_NOT_COVERED, QUERY_STATUS_ERROR)


LIVE_PENDING = "pending"
LIVE_RUNNING = "running"
LIVE_COMPLETED = "completed"
LIVE_CANCELED = "canceled"
LIVE_STATUSES = (LIVE_PENDING, LIVE_RUNNING, LIVE_COMPLETED, LIVE_CANCELED)

# Bounds. A live query is typed by a human at a console and fanned out to a
# fleet, so every one of these is a guard against a keystroke costing more
# than it should.
DEFAULT_LIVE_CONCURRENCY = 20
DEFAULT_LIVE_TIMEOUT_SECONDS = 120


def _utcnow() -> datetime:
    """Naive-UTC now, matching the shared/tenant timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# shared partition -- the curated catalog, one copy for every customer
# ---------------------------------------------------------------------------


class SharedQueryPack(Base):
    """A curated query pack. Global reference data, never per tenant."""

    __tablename__ = "shared_query_pack"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_shared_query_pack_slug"),
        Index("ix_shared_query_pack_enabled", "deprecated"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Stable identity across catalog refreshes.  The id is a local uuid and a
    # re-ingest would mint a new one; the slug is what an assignment survives
    # on, and what an offline bundle is keyed by.
    slug = Column(String(128), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Catalog version, bumped by the publisher when the queries change.  An
    # assignment records the version it last ran, so "this pack changed under
    # you" is answerable rather than inferred from timestamps.
    version = Column(Integer, nullable=False, default=1)
    category = Column(String(64), nullable=True, index=True)
    # Retired rather than deleted: an assignment may still name it, and the
    # operator deserves "this pack was withdrawn" over a dangling reference.
    deprecated = Column(Boolean, nullable=False, default=False)
    source = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    queries = relationship(
        "SharedQueryPackQuery",
        back_populates="pack",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
    )

    def __repr__(self):
        return f"<SharedQueryPack(slug={self.slug}, version={self.version})>"


class SharedQueryPackQuery(Base):
    """One query inside a curated pack."""

    __tablename__ = "shared_query_pack_query"
    __table_args__ = (
        UniqueConstraint(
            "shared_pack_id", "name", name="uq_shared_query_pack_query_name"
        ),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Same partition as its pack, so a real FK is correct here.
    shared_pack_id = Column(
        GUID(),
        ForeignKey(SHARED_PACK_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    name = Column(String(128), nullable=False)
    sql = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    # Which contract tables this query reads.  DECLARED, not parsed: the agent
    # compares it against its own coverage to decide whether the query can be
    # answered honestly here, and guessing it from the SQL would be wrong in
    # exactly the cases that matter (a join, a subquery, a CTE).
    required_tables = Column(JSON, nullable=True)
    interval_minutes = Column(Integer, nullable=False, default=DEFAULT_INTERVAL_MINUTES)
    platforms = Column(JSON, nullable=True)

    pack = relationship("SharedQueryPack", back_populates="queries")

    def __repr__(self):
        return f"<SharedQueryPackQuery(name={self.name})>"


# ---------------------------------------------------------------------------
# tenant partition -- what a customer wrote, assigned, and got back
# ---------------------------------------------------------------------------


class QueryPack(Base):
    """A pack a customer wrote. Tenant data, never shared."""

    __tablename__ = "query_pack"
    __table_args__ = (UniqueConstraint("name", name="uq_query_pack_name"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    queries = relationship(
        "QueryPackQuery", back_populates="pack", cascade=CASCADE_ALL_DELETE_ORPHAN
    )
    assignments = relationship(
        "QueryPackAssignment", back_populates="pack", cascade=CASCADE_ALL_DELETE_ORPHAN
    )

    def __repr__(self):
        return f"<QueryPack(name={self.name}, version={self.version})>"


class QueryPackQuery(Base):
    """One query inside a tenant-authored pack."""

    __tablename__ = "query_pack_query"
    __table_args__ = (
        UniqueConstraint("pack_id", "name", name="uq_query_pack_query_name"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    pack_id = Column(
        GUID(),
        ForeignKey(PACK_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    name = Column(String(128), nullable=False)
    sql = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    required_tables = Column(JSON, nullable=True)
    interval_minutes = Column(Integer, nullable=False, default=DEFAULT_INTERVAL_MINUTES)
    platforms = Column(JSON, nullable=True)

    pack = relationship("QueryPack", back_populates="queries")

    def __repr__(self):
        return f"<QueryPackQuery(name={self.name})>"


class QueryPackAssignment(Base):
    """Which hosts run which pack — the multi-tenant policy itself.

    Exactly one of ``pack_id`` (tenant-authored) and ``shared_pack_id``
    (curated) is set.  ``shared_pack_id`` has NO ForeignKey on purpose: it
    crosses a partition boundary, and under scale-out the shared catalog is a
    separate database where the constraint could not be enforced anyway.
    """

    __tablename__ = "query_pack_assignment"
    __table_args__ = (
        # The tick's query is "enabled assignments, by target"; without this
        # it scans every assignment on every pass.
        Index("ix_query_pack_assignment_enabled", "enabled", "pack_id"),
        Index("ix_query_pack_assignment_shared", "enabled", "shared_pack_id"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    pack_id = Column(
        GUID(), ForeignKey(PACK_ID_FK, ondelete=CASCADE_DELETE), nullable=True
    )
    # SOFT reference to shared_query_pack.id — see the class docstring.
    shared_pack_id = Column(GUID(), nullable=True, index=True)
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
    # The catalog version last dispatched, so "the curated pack changed" is a
    # fact rather than a timestamp comparison.
    last_pack_version = Column(Integer, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    last_dispatched_at = Column(DateTime, nullable=True)

    pack = relationship("QueryPack", back_populates="assignments")

    def __repr__(self):
        target = self.host_id or self.tag_id or self.site_id
        return f"<QueryPackAssignment(id={self.id}, target={target})>"


class QueryPackLiveQuery(Base):
    """One ad-hoc query fanned out across a fleet — ROADMAP 21.1 S5.

    WHY THIS IS NOT JUST A PACK WITH ONE QUERY
    -------------------------------------------
    It is dispatched as one, deliberately, so the agent needs no new command
    and the result path is the one S4 already proved. What a pack does NOT
    carry is the thing this table exists for: an operator typed this at a
    console and pointed it at a fleet, so it needs BOUNDS — how many hosts may
    be in flight at once, how long to wait for a silent one, and how many rows
    a single host may return.

    Unbounded fan-out is the failure mode fleet jobs were built to replace,
    and a live query is the easiest possible way to reintroduce it: one
    keystroke, four thousand hosts. So the bounds are columns on the request
    rather than a policy somewhere else, and they are recorded with the query
    — what a run actually did stays answerable after the fact.

    WHY RESULTS LIVE IN ``query_pack_run``
    --------------------------------------
    A target is a run: same host, same per-query outcomes, same grading, same
    "not covered is not empty" property. A second results table would need its
    own copy of all of that, and the two would drift.
    """

    __tablename__ = "query_pack_live_query"
    __table_args__ = (
        # NOT "ix_query_pack_live_query_status": that is the name SQLAlchemy
        # auto-generates for ``status`` because the column carries
        # index=True, and the two collide at create_all with "index already
        # exists". Named for both columns, which reads better anyway.
        Index("ix_query_pack_live_query_status_created", "status", "created_at"),
    )

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    # Optional: an operator may name a query worth recognising later, but
    # most are one-offs and forcing a name would just produce "test" a lot.
    name = Column(String(255), nullable=True)
    sql = Column(Text, nullable=False)
    # DECLARED by the author, same contract as a pack query -- the agent
    # compares it against its own coverage so a host that cannot answer says
    # so rather than erroring.
    required_tables = Column(JSON, nullable=True)

    status = Column(String(20), nullable=False, default=LIVE_PENDING, index=True)
    # How many targets may be in flight at once. Clamped by the engine.
    concurrency = Column(Integer, nullable=False, default=DEFAULT_LIVE_CONCURRENCY)
    # A host that never answers must not hold a slot forever -- without this
    # one unreachable machine stalls the wave behind it indefinitely.
    timeout_seconds = Column(
        Integer, nullable=False, default=DEFAULT_LIVE_TIMEOUT_SECONDS
    )

    total_targets = Column(Integer, nullable=False, default=0)
    completed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    # Counted SEPARATELY from failures: a host that does not serve the tables
    # has not failed, and folding it into failed_count would make a Windows
    # box look broken for lacking ``mounts``.
    not_covered_count = Column(Integer, nullable=False, default=0)

    requested_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<QueryPackLiveQuery(id={self.id}, status={self.status}, "
            f"targets={self.total_targets})>"
        )


class QueryPackRun(Base):
    """One execution of one pack on one host."""

    __tablename__ = "query_pack_run"
    __table_args__ = (Index("ix_query_pack_run_host_started", "host_id", "started_at"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4, index=True)
    assignment_id = Column(GUID(), nullable=True, index=True)
    # Phase 21.1 S5. A run belongs to an ASSIGNMENT (scheduled) or a LIVE
    # QUERY (ad-hoc), never both. Reusing this table rather than adding a
    # parallel one is what lets the agent and the result handler stay
    # untouched: a live query is dispatched as a one-query pack and its
    # results correlate on ``run_id`` exactly as a scheduled run does.
    live_query_id = Column(GUID(), nullable=True, index=True)
    pack_id = Column(GUID(), nullable=True, index=True)
    shared_pack_id = Column(GUID(), nullable=True, index=True)
    pack_name = Column(String(255), nullable=True)
    host_id = Column(
        GUID(),
        ForeignKey(HOST_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False, default=RUN_STATUS_PENDING)
    # The fact contract version the AGENT ran against.  Recorded per run
    # because a fleet upgrades gradually: without it, comparing results across
    # hosts silently compares different contracts.
    contract_version = Column(Integer, nullable=True)
    queries_total = Column(Integer, nullable=False, default=0)
    queries_ok = Column(Integer, nullable=False, default=0)
    queries_not_covered = Column(Integer, nullable=False, default=0)
    queries_failed = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    results = relationship(
        "QueryPackResultRow", back_populates="run", cascade=CASCADE_ALL_DELETE_ORPHAN
    )

    def __repr__(self):
        return f"<QueryPackRun(host_id={self.host_id}, status={self.status})>"


class QueryPackResultRow(Base):
    """One row returned by one query in one run.

    ``columns`` holds the row as JSON because a pack's shape is whatever its
    SQL selects — there is no fixed column set to model. The rest is indexed so
    S6's consumers can ask "which hosts returned a row for query X" without
    reading the payloads.
    """

    __tablename__ = "query_pack_result_row"
    __table_args__ = (Index("ix_query_pack_result_query", "run_id", "query_name"),)

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        GUID(),
        ForeignKey(RUN_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    query_name = Column(String(128), nullable=False)
    # ``ok`` / ``not_covered`` / ``error``.  A ``not_covered`` query gets ONE
    # row with a null payload — it is a record that the question was asked and
    # could not be answered here, which is different from asking and getting
    # nothing back, and different again from never asking.
    status = Column(String(32), nullable=False, default=QUERY_STATUS_OK)
    reason = Column(String(64), nullable=True)
    columns = Column(JSON, nullable=True)
    collected_at = Column(DateTime, nullable=False, default=_utcnow)

    run = relationship("QueryPackRun", back_populates="results")

    def __repr__(self):
        return f"<QueryPackResultRow(query={self.query_name}, status={self.status})>"
