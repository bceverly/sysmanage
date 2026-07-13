"""create release_upgrade_job (tenant partition) — Phase 14.3

Operator-driven, schedulable distro release-upgrade jobs live in the TENANT
partition (unprefixed) — per-host operational state.  ``scheduled_at`` makes a
job maintenance-window aware (the same dispatch 14.2 gates).  ``host_id`` is a
real intra-partition FK to ``host.id`` (host is tenant-partition too).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r1relupgrade
Revises: q1appladv
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "r1relupgrade"
down_revision: Union[str, None] = "q1appladv"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "release_upgrade_job"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("from_os_name", sa.String(length=100), nullable=True),
        sa.Column("from_version", sa.String(length=50), nullable=True),
        sa.Column("to_version", sa.String(length=50), nullable=True),
        sa.Column("method", sa.String(length=50), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("precheck_results", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_release_upgrade_job_host_id", _TABLE, ["host_id"])
    op.create_index("ix_release_upgrade_job_status", _TABLE, ["status"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
