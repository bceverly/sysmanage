# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-by-fleet rollout of automatic updates (ROADMAP 26.4, Enterprise).

* ``upgrade_profiles``: ``rollout_enabled`` (off: every host as 26.1-26.3)
  and ``rollout_max_failure_pct`` (the share of a fleet's runs that may fail
  before the rollout halts; 0: any failure halts it)
* ``upgrade_profile_rollout_stage``: a policy's fleets, in order -- a name,
  the tag that selects the fleet's hosts, and its soak time in minutes
* ``auto_update_rollout``: one rollout of a policy -- its fleets and their
  hosts as planned when it started, the fleet it is on, and why it halted
* ``auto_update_run.rollout_id`` / ``rollout_stage``: the rollout and fleet
  a run belongs to (NULL outside a rollout)

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q96autoupdaterollout
Revises: q95autoupdatetiming
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q96autoupdaterollout"
down_revision: Union[str, None] = "q95autoupdatetiming"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _tables():
    return {
        "upgrade_profile_rollout_stage": [
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "profile_id",
                GUID(),
                sa.ForeignKey("upgrade_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column(
                "tag_id",
                GUID(),
                sa.ForeignKey("tags.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("soak_minutes", sa.Integer(), nullable=False, server_default="0"),
        ],
        "auto_update_rollout": [
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "profile_id",
                GUID(),
                sa.ForeignKey("upgrade_profiles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("profile_name", sa.String(120), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stages", sa.JSON(), nullable=True),
            sa.Column("triggered_by", sa.String(255), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("halt_reason", sa.String(40), nullable=True),
            sa.Column("halt_detail", sa.JSON(), nullable=True),
            sa.Column("halted_at", sa.DateTime(), nullable=True),
            sa.Column("ended_by", sa.String(255), nullable=True),
            sa.Column("end_reason", sa.String(1000), nullable=True),
        ],
    }


def _columns():
    return {
        "upgrade_profiles": [
            sa.Column(
                "rollout_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "rollout_max_failure_pct",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        ],
        "auto_update_run": [
            sa.Column("rollout_id", GUID(), nullable=True),
            sa.Column("rollout_stage", sa.Integer(), nullable=True),
        ],
    }


_INDEXES = (
    (
        "upgrade_profile_rollout_stage",
        "ix_upgrade_profile_rollout_stage_profile_id",
        ["profile_id"],
    ),
    ("auto_update_rollout", "ix_auto_update_rollout_profile_id", ["profile_id"]),
    ("auto_update_rollout", "ix_auto_update_rollout_status", ["status"]),
    ("auto_update_run", "ix_auto_update_run_rollout_id", ["rollout_id"]),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, columns in _tables().items():
        if table not in tables:
            op.create_table(table, *columns)
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in have:
                op.add_column(table, column)
    inspector = inspect(op.get_bind())
    for table, name, cols in _INDEXES:
        if table in inspector.get_table_names():
            if name not in {i["name"] for i in inspector.get_indexes(table)}:
                op.create_index(name, table, cols)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, name, _cols in _INDEXES:
        if table in tables and name in {
            i["name"] for i in inspector.get_indexes(table)
        }:
            op.drop_index(name, table_name=table)
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name in have:
                    batch.drop_column(column.name)
    for table in ("auto_update_rollout", "upgrade_profile_rollout_stage"):
        if table in tables:
            op.drop_table(table)
