# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet restore jobs (27.2, Enterprise, 2026-11-24).

``backup_fleet_restore``: one restore asked of many hosts -- the paths, the
snapshot rule (newest, or newest before a moment), staging or in place, and
how many hosts at once.  ``backup_fleet_restore_target``: one row per host,
with the snapshot it restores, its run and its outcome.  Pure additive
CREATE TABLEs; idempotent and identical on SQLite and PostgreSQL.

Revision ID: q114fleetrestore
Revises: q113reenroll
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "q114fleetrestore"
down_revision: Union[str, None] = "q113reenroll"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_JOB = "backup_fleet_restore"
_TARGET = "backup_fleet_restore_target"


def _guid():
    if op.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    guid = _guid()
    if _JOB not in tables:
        op.create_table(
            _JOB,
            sa.Column("id", guid, primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("include", sa.Text(), nullable=False),
            sa.Column("exclude", sa.Text(), nullable=True),
            sa.Column("before_at", sa.DateTime(), nullable=True),
            sa.Column(
                "in_place", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "dry_run", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "allow_unsigned",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("concurrency", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("status", sa.String(24), nullable=False, index=True),
            sa.Column("created_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_by", sa.String(255), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
    if _TARGET not in tables:
        op.create_table(
            _TARGET,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "job_id",
                guid,
                sa.ForeignKey(_JOB + ".id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "host_id",
                guid,
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("status", sa.String(16), nullable=False, index=True),
            sa.Column("snapshot", sa.String(255), nullable=True),
            sa.Column("run_id", guid, nullable=True),
            sa.Column("message", sa.String(500), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (_TARGET, _JOB):
        if table in tables:
            op.drop_table(table)
