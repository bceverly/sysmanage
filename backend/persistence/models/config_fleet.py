# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-scale configuration management: inventories and jobs (Phase 20.1).

Its own module rather than more rows in ``config_management.py`` for the reason
that file gives for existing at all: one file per feature keeps each readable.
Profiles answer "what should be true"; this answers "on which thousand hosts,
and how fast".

THE PROBLEM THIS SCHEMA EXISTS TO SOLVE
---------------------------------------
``ConfigProfileAssignment`` already binds a profile to a host, a tag or a site
and fires it on a cron. It queues every matched host in one pass, which is
correct for tens and wrong for thousands: one transaction holding the whole
fleet, and a queue burst that arrives all at once regardless of what the
network or the database can absorb.

A ``ConfigJob`` is that same fan-out made OBSERVABLE and BOUNDED. Observable
because every target is a row with its own status, so "which 12 of the 4,000
failed" is a query rather than a log trawl. Bounded because the job carries a
``concurrency`` and the runner only ever has that many targets in flight, so
the fleet is worked through in waves instead of being shouted at.

WHY A JOB IS NOT JUST A BIGGER ASSIGNMENT
-----------------------------------------
They answer different questions and are deliberately not merged. An assignment
is standing intent -- "this profile applies here, forever, on this schedule".
A job is one bounded EXECUTION with a beginning, an end and a result you can
point at afterwards. Collapsing them would mean either giving standing intent
a completion state it can never reach, or giving a finished run a cron.

WHY HISTORY OUTLIVES ITS PARENTS
--------------------------------
``template_id``, ``profile_id`` and ``host_id`` all soften to NULL on delete
and every one of them is shadowed by a denormalised name. The record that four
thousand hosts were changed last Tuesday is an audit artifact; deleting the
template that did it must not erase the evidence, which is the same rule
``config_profile_run.profile_id`` already follows.
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
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID

HOST_ID_FK = "host.id"
CASCADE_DELETE = "CASCADE"
SET_NULL = "SET NULL"
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"
INVENTORY_ID_FK = "config_inventory.id"
PROFILE_ID_FK = "config_profile.id"

# Job and target lifecycles. Plain strings rather than a DB enum: every other
# status column in this schema is a string, and an enum type is the one thing
# SQLite and PostgreSQL disagree about badly enough to make migrations awkward.
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"
JOB_CANCELED = "canceled"

TARGET_PENDING = "pending"
TARGET_QUEUED = "queued"
TARGET_SUCCEEDED = "succeeded"
TARGET_FAILED = "failed"
TARGET_SKIPPED = "skipped"

# In flight from the server's point of view: dispatched, no result yet. The
# runner counts these to decide how many more it may release.
TARGET_IN_FLIGHT = (TARGET_QUEUED,)
TARGET_TERMINAL = (TARGET_SUCCEEDED, TARGET_FAILED, TARGET_SKIPPED)


class ConfigInventory(Base):
    """A named, reusable set of hosts to run configuration against.

    The roadmap asks for "inventories from SysManage hosts/tags/sites", and
    that phrasing is the design: an inventory does not COPY a host list, it
    names the same three selectors assignments already use and resolves them
    at launch. A copied list is wrong the moment a host is added to a tag, and
    wrong silently -- the run simply misses machines nobody notices are absent.

    ``all_hosts`` is a separate flag rather than a member row meaning
    "everything", because "the entire fleet" is a different and more dangerous
    statement than any selector, and it should be visible as such in the row
    rather than inferred from an empty member list -- which is also what an
    inventory somebody has not finished building looks like.
    """

    __tablename__ = "config_inventory"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    # Every active host. Members are ignored when this is set.
    all_hosts = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    members = relationship(
        "ConfigInventoryMember",
        back_populates="inventory",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
        passive_deletes=True,
    )

    def __repr__(self):
        return (
            f"<ConfigInventory(id={self.id}, name='{self.name}', "
            f"all_hosts={self.all_hosts})>"
        )


class ConfigInventoryMember(Base):
    """One selector in an inventory: a host, a tag or a site.

    Three nullable foreign keys with exactly one set, matching
    ``ConfigProfileAssignment`` exactly. The reasoning carries over unchanged:
    a ``(kind, id)`` pair cannot be a foreign key, so it would let a member
    outlive the host it names and the first symptom would be a fleet job
    dispatching at a machine that no longer exists.

    Members UNION. An inventory of "tag=web" plus "site=eu-west" is every host
    in either, not the intersection -- intersection is expressible by tagging
    and union is what an operator building a target list actually reaches for.
    """

    __tablename__ = "config_inventory_member"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    inventory_id = Column(
        GUID(),
        ForeignKey(INVENTORY_ID_FK, ondelete=CASCADE_DELETE),
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
    created_at = Column(DateTime, nullable=False)

    inventory = relationship("ConfigInventory", back_populates="members")

    def __repr__(self):
        target = self.host_id or self.tag_id or self.site_id
        return f"<ConfigInventoryMember(inventory={self.inventory_id}, {target})>"


class ConfigJobTemplate(Base):
    """A profile plus an inventory plus how to run it: a launchable unit.

    This is the "job template" the roadmap names. Its value is that the three
    decisions an operator would otherwise re-make every time -- which profile,
    against whom, how aggressively -- are made ONCE and named, so the run that
    happens at 3am under a schedule is provably the run somebody reviewed.

    ``concurrency`` is stored per template rather than configured globally
    because the right value is a property of the WORK: a package-install
    profile against a shared mirror wants a small number, a file-permissions
    profile can safely saturate. A single server-wide setting would be tuned
    for the worst case and waste the rest.

    ``schedule`` makes a template a standing fleet job. It is derived-due like
    ``ConfigProfileAssignment`` and for the identical reason -- see
    ``last_launched_at`` -- so a server that was down overnight launches once
    on the next tick instead of replaying every occurrence it slept through.
    """

    __tablename__ = "config_job_template"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    # CASCADE: a template without its profile has nothing to run, so it is
    # not a record worth keeping. Contrast ConfigJob.profile_id, which is a
    # historical record and softens to NULL instead.
    profile_id = Column(
        GUID(),
        ForeignKey(PROFILE_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    inventory_id = Column(
        GUID(),
        ForeignKey(INVENTORY_ID_FK, ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    # A template that only ever reports drift, never fixes it.
    check_mode = Column(Boolean, nullable=False, default=False)
    # How many targets may be in flight at once. The engine clamps it; this
    # column stores what the engine allowed, not what was typed.
    concurrency = Column(Integer, nullable=False, default=20)
    timeout_seconds = Column(Integer, nullable=True)
    schedule = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    # Anchor for derived due-ness. There is deliberately no ``next_run``: a
    # stored cursor has to be migrated when added, kept correct when the cron
    # changes and repaired when it drifts, and each is a way for a schedule to
    # stop firing with nothing to show for it.
    last_launched_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # The tick's query is "enabled templates that have a cron".
        Index("ix_config_job_template_scheduled", "enabled", "schedule"),
    )

    def __repr__(self):
        return f"<ConfigJobTemplate(id={self.id}, name='{self.name}')>"


class ConfigJob(Base):
    """One fan-out of a profile across an inventory.

    Every identifying field is shadowed by a denormalised name, and every
    foreign key softens to NULL. A job is the audit record that a fleet-wide
    change happened; deleting the template afterwards must leave that record
    readable, not turn it into a row of nulls nobody can interpret.

    The counters are maintained by the runner rather than computed from
    ``ConfigJobTarget`` on every read. A job of four thousand targets would
    otherwise aggregate four thousand rows each time somebody opened the page,
    and the list view shows many jobs at once.
    """

    __tablename__ = "config_job"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        GUID(),
        ForeignKey("config_job_template.id", ondelete=SET_NULL),
        nullable=True,
        index=True,
    )
    template_name = Column(String(255), nullable=True)
    profile_id = Column(
        GUID(), ForeignKey(PROFILE_ID_FK, ondelete=SET_NULL), nullable=True
    )
    profile_name = Column(String(255), nullable=True)
    inventory_name = Column(String(255), nullable=True)

    status = Column(String(20), nullable=False, default=JOB_PENDING, index=True)
    check_mode = Column(Boolean, nullable=False, default=False)
    concurrency = Column(Integer, nullable=False, default=20)
    timeout_seconds = Column(Integer, nullable=True)

    total_targets = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)

    # NULL when a schedule launched it -- there is no operator to name, and
    # inventing one ("system") would make an audit trail lie about who acted.
    requested_by = Column(String(255), nullable=True)
    # Why it stopped, when it stopped badly. A job that failed to dispatch at
    # all is otherwise indistinguishable from one whose hosts all failed.
    detail = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    targets = relationship(
        "ConfigJobTarget",
        back_populates="job",
        cascade=CASCADE_ALL_DELETE_ORPHAN,
        passive_deletes=True,
    )

    __table_args__ = (
        # The runner's query is "jobs still needing work, oldest first"; the
        # list view's is "recent jobs". Both are served by this.
        Index("ix_config_job_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ConfigJob(id={self.id}, profile='{self.profile_name}', "
            f"status={self.status}, targets={self.total_targets})>"
        )


class ConfigJobTarget(Base):
    """One host within a job, and what became of it.

    A row per host is what makes a fleet job answerable. Without it a job of
    four thousand hosts reports a single success or failure, and "which ones
    failed, and why" becomes a log search across an hour of dispatch.

    ``command_id`` is the join back to the result. The agent echoes the
    envelope's ``message_id`` as ``command_id`` on the result it sends, so
    storing it here is what lets an arriving ``config_profile_run`` close the
    target that produced it. Getting this wrong once already cost Phase 20.1 a
    round of silently dropped results (2026-08-28), which is why the dispatch
    helper generates ONE id for the envelope and the queue row both.
    """

    __tablename__ = "config_job_target"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        GUID(),
        ForeignKey("config_job.id", ondelete=CASCADE_DELETE),
        nullable=False,
        index=True,
    )
    # SET NULL with the fqdn shadowed beside it: decommissioning a host must
    # not rewrite the history of a job that ran against it.
    host_id = Column(
        GUID(), ForeignKey(HOST_ID_FK, ondelete=SET_NULL), nullable=True, index=True
    )
    host_fqdn = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default=TARGET_PENDING)
    command_id = Column(String(36), nullable=True, index=True)
    # The run this target produced, so the UI can link to the task detail
    # rather than storing a second copy of it.
    run_id = Column(GUID(), nullable=True)
    # Why it was skipped or how it failed -- "agent does not advertise
    # config-management support" is the single most common answer and is not
    # an error, so it needs somewhere to be said plainly.
    detail = Column(Text, nullable=True)
    queued_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    job = relationship("ConfigJob", back_populates="targets")

    __table_args__ = (
        # The runner asks "how many of this job are in flight" and "give me
        # the next N pending" on every tick; both are this index.
        Index("ix_config_job_target_job_status", "job_id", "status"),
    )

    def __repr__(self):
        return (
            f"<ConfigJobTarget(job={self.job_id}, host='{self.host_fqdn}', "
            f"status={self.status})>"
        )
