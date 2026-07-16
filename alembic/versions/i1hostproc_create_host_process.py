# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create host_process (Phase 13.3 — Process Management)

Stores the latest running-process snapshot reported by each host's agent.
The ingest handler replaces all rows for a host on every snapshot, so this is
a current-state table, not a time series.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: i1hostproc
Revises: h1userinvite
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "i1hostproc"
down_revision: Union[str, None] = "h1userinvite"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host_process"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("parent_pid", sa.Integer(), nullable=True),
        sa.Column("process_name", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("memory_rss_bytes", sa.BigInteger(), nullable=True),
        sa.Column("command_line", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_host_process_host_id", _TABLE, ["host_id"])
    op.create_index("ix_host_process_pid", _TABLE, ["pid"])
    op.create_index("ix_host_process_process_name", _TABLE, ["process_name"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_TABLE)
