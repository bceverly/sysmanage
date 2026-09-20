# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add fleet-scale config jobs and remediation rules for Phase 20.1.

Five tables closing the last two feature boxes of Phase 20:

* ``config_inventory`` / ``config_inventory_member`` -- named, reusable host
  selections built from the same host/tag/site selectors assignments use.
* ``config_job_template`` -- a profile plus an inventory plus how hard to run
  it, launchable on demand or on a cron.
* ``config_job`` / ``config_job_target`` -- one bounded fan-out, with a row per
  host so "which twelve of the four thousand failed" is a query.
* ``config_remediation_rule`` -- the binding from a drift finding to the
  profile that repairs it. Deliberately only the binding: the playbook body is
  a ``config_profile``, so authoring, versioning, spec building and run history
  are all reused rather than re-grown.

Idempotent: every create is guarded by ``inspect().has_table()``, so re-running
against a partially-migrated database is a no-op. SQLite- and PostgreSQL-safe:
plain CREATE TABLE with every constraint declared INLINE. That last part is not
style -- a UniqueConstraint added afterwards is an ALTER, which SQLite cannot
do, and the tenant chain is exercised on SQLite by
tests/test_alembic_prefix_guard.py. c21cfgprof01 shipped with exactly that
mistake and only CI caught it.

Revision ID: c23cfgfleet01
Revises: c22cfgdrift01
"""

import sqlalchemy as sa
from alembic import op

from backend.persistence.models.core import GUID

revision = "c23cfgfleet01"
down_revision = "c22cfgdrift01"
branch_labels = None
depends_on = None

_INVENTORY = "config_inventory"
_MEMBER = "config_inventory_member"
_TEMPLATE = "config_job_template"
_JOB = "config_job"
_TARGET = "config_job_target"
_RULE = "config_remediation_rule"

_HOST_FK = "host.id"
_PROFILE_FK = "config_profile.id"
_CASCADE = "CASCADE"
_SET_NULL = "SET NULL"


def _create_inventory() -> None:
    op.create_table(
        _INVENTORY,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("all_hosts", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(f"ix_{_INVENTORY}_name", _INVENTORY, ["name"])


def _create_member() -> None:
    op.create_table(
        _MEMBER,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "inventory_id",
            GUID(),
            sa.ForeignKey(f"{_INVENTORY}.id", ondelete=_CASCADE),
            nullable=False,
        ),
        # Exactly one of the three is set. Three real foreign keys rather than
        # a (kind, id) pair, which could not be one -- and a member that
        # outlives the host it names is a job dispatching at a decommissioned
        # machine.
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey(_HOST_FK, ondelete=_CASCADE),
            nullable=True,
        ),
        sa.Column(
            "tag_id",
            GUID(),
            sa.ForeignKey("tags.id", ondelete=_CASCADE),
            nullable=True,
        ),
        sa.Column(
            "site_id",
            GUID(),
            sa.ForeignKey("federation_sites.id", ondelete=_CASCADE),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(f"ix_{_MEMBER}_inventory_id", _MEMBER, ["inventory_id"])


def _create_template() -> None:
    op.create_table(
        _TEMPLATE,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        # CASCADE: a template without its profile has nothing to run.
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey(_PROFILE_FK, ondelete=_CASCADE),
            nullable=False,
        ),
        sa.Column(
            "inventory_id",
            GUID(),
            sa.ForeignKey(f"{_INVENTORY}.id", ondelete=_CASCADE),
            nullable=False,
        ),
        sa.Column(
            "check_mode", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("schedule", sa.String(100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_launched_at", sa.DateTime(), nullable=True),
    )
    op.create_index(f"ix_{_TEMPLATE}_name", _TEMPLATE, ["name"])
    op.create_index(f"ix_{_TEMPLATE}_profile_id", _TEMPLATE, ["profile_id"])
    op.create_index(f"ix_{_TEMPLATE}_inventory_id", _TEMPLATE, ["inventory_id"])
    op.create_index(f"ix_{_TEMPLATE}_scheduled", _TEMPLATE, ["enabled", "schedule"])


def _create_job() -> None:
    op.create_table(
        _JOB,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        # Every parent softens to NULL and is shadowed by a denormalised name:
        # a job is the audit record that a fleet-wide change happened, and
        # deleting the template afterwards must not reduce it to nulls.
        sa.Column(
            "template_id",
            GUID(),
            sa.ForeignKey(f"{_TEMPLATE}.id", ondelete=_SET_NULL),
            nullable=True,
        ),
        sa.Column("template_name", sa.String(255), nullable=True),
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey(_PROFILE_FK, ondelete=_SET_NULL),
            nullable=True,
        ),
        sa.Column("profile_name", sa.String(255), nullable=True),
        sa.Column("inventory_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "check_mode", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("total_targets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(f"ix_{_JOB}_template_id", _JOB, ["template_id"])
    op.create_index(f"ix_{_JOB}_status", _JOB, ["status"])
    op.create_index(f"ix_{_JOB}_status_created", _JOB, ["status", "created_at"])


def _create_target() -> None:
    op.create_table(
        _TARGET,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            GUID(),
            sa.ForeignKey(f"{_JOB}.id", ondelete=_CASCADE),
            nullable=False,
        ),
        # SET NULL with the fqdn shadowed beside it: decommissioning a host
        # must not rewrite the history of a job that ran against it.
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey(_HOST_FK, ondelete=_SET_NULL),
            nullable=True,
        ),
        sa.Column("host_fqdn", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # The join back to the arriving result: the agent echoes the envelope's
        # message_id as command_id, and this is what closes the target.
        sa.Column("command_id", sa.String(36), nullable=True),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(f"ix_{_TARGET}_job_id", _TARGET, ["job_id"])
    op.create_index(f"ix_{_TARGET}_host_id", _TARGET, ["host_id"])
    op.create_index(f"ix_{_TARGET}_command_id", _TARGET, ["command_id"])
    op.create_index(f"ix_{_TARGET}_job_status", _TARGET, ["job_id", "status"])


def _create_rule() -> None:
    op.create_table(
        _RULE,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        # SET NULL: deleting the profile a rule was SCOPED to should widen the
        # rule, not delete the repair. A widened rule still works and is
        # visible; a vanished one is a repair that stops with no trace.
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey(_PROFILE_FK, ondelete=_SET_NULL),
            nullable=True,
        ),
        sa.Column("task_pattern", sa.String(500), nullable=False),
        # CASCADE, unlike profile_id above: a rule whose REMEDIATION is gone
        # has nothing to run.
        sa.Column(
            "remediation_profile_id",
            GUID(),
            sa.ForeignKey(_PROFILE_FK, ondelete=_CASCADE),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "auto_apply", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(f"ix_{_RULE}_name", _RULE, ["name"])
    op.create_index(f"ix_{_RULE}_profile_id", _RULE, ["profile_id"])
    op.create_index(
        f"ix_{_RULE}_remediation_profile_id", _RULE, ["remediation_profile_id"]
    )
    op.create_index(f"ix_{_RULE}_active", _RULE, ["enabled", "auto_apply", "priority"])


# Creation order matters: members and templates reference the inventory, and
# targets reference the job.
_BUILDERS = (
    (_INVENTORY, _create_inventory),
    (_MEMBER, _create_member),
    (_TEMPLATE, _create_template),
    (_JOB, _create_job),
    (_TARGET, _create_target),
    (_RULE, _create_rule),
)


def upgrade() -> None:
    """Create the fleet-job and remediation-rule tables."""
    inspector = sa.inspect(op.get_bind())
    for table, build in _BUILDERS:
        if not inspector.has_table(table):
            build()


def downgrade() -> None:
    """Drop them, children first."""
    inspector = sa.inspect(op.get_bind())
    for table, _build in reversed(_BUILDERS):
        if inspector.has_table(table):
            op.drop_table(table)
