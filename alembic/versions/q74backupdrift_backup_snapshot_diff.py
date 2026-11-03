# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Drift timeline (Pro+ backup_engine, ROADMAP 24.7, 2026-11-02)

Tenant data.  ``backup_snapshot_diff`` keeps what changed between two
snapshots of a host's repository -- restate ``diff --packages`` run on the
host after each capture: counts, the first 1000 file changes and the first
1000 package changes (JSON).  ``backup_policy`` gains ``drift_ignore``: the
paths the timeline hides as expected churn on that host (JSON list of
restate patterns).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q74backupdrift
Revises: q73backupsigning
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q74backupdrift"
down_revision: Union[str, None] = "q73backupsigning"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLE = "backup_snapshot_diff"
_POLICY = (("drift_ignore", sa.Text()),)


def _tables(insp):
    return set(insp.get_table_names())


def _add_policy_columns(insp) -> None:
    if "backup_policy" not in _tables(insp):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    for name, kind in _POLICY:
        if name not in present:
            op.add_column("backup_policy", sa.Column(name, kind, nullable=True))


def _create_table(insp) -> None:
    if TABLE in _tables(insp) or "backup_policy" not in _tables(insp):
        return
    op.create_table(
        TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "policy_id",
            GUID(),
            sa.ForeignKey("backup_policy.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_snapshot", sa.String(255), nullable=False),
        sa.Column("to_snapshot", sa.String(255), nullable=False),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("added", sa.Integer(), nullable=True),
        sa.Column("deleted", sa.Integer(), nullable=True),
        sa.Column("modified", sa.Integer(), nullable=True),
        sa.Column("packages_changed", sa.Integer(), nullable=True),
        sa.Column("explained", sa.Integer(), nullable=True),
        sa.Column("changes", sa.Text(), nullable=True),
        sa.Column("packages", sa.Text(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "packages_truncated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "policy_id", "from_snapshot", "to_snapshot", name="uq_backup_snapshot_diff"
        ),
    )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add_policy_columns(insp)
    _create_table(insp)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if TABLE in _tables(insp):
        op.drop_table(TABLE)
    if "backup_policy" in _tables(insp):
        present = {c["name"] for c in insp.get_columns("backup_policy")}
        drop = [name for name, _kind in _POLICY if name in present]
        if drop:
            with op.batch_alter_table("backup_policy") as batch:
                for name in drop:
                    batch.drop_column(name)
