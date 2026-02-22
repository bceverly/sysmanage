"""add_reboot_orchestration_table

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-02-22 12:00:00.000000

Adds the reboot_orchestration table for tracking orchestrated reboot
sequences on parent hosts with running child hosts (Phase 2.5).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, None] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    is_postgresql = conn.dialect.name == "postgresql"

    if "reboot_orchestration" not in tables:
        if is_postgresql:
            op.create_table(
                "reboot_orchestration",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("parent_host_id", sa.UUID(), nullable=False),
                sa.Column(
                    "status",
                    sa.String(length=50),
                    nullable=False,
                    server_default="pending_shutdown",
                ),
                sa.Column("child_hosts_snapshot", sa.Text(), nullable=False),
                sa.Column("child_hosts_restart_status", sa.Text(), nullable=True),
                sa.Column(
                    "shutdown_timeout_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default="120",
                ),
                sa.Column("initiated_by", sa.String(length=255), nullable=False),
                sa.Column("initiated_at", sa.DateTime(), nullable=False),
                sa.Column("shutdown_completed_at", sa.DateTime(), nullable=True),
                sa.Column("reboot_issued_at", sa.DateTime(), nullable=True),
                sa.Column("agent_reconnected_at", sa.DateTime(), nullable=True),
                sa.Column("restart_completed_at", sa.DateTime(), nullable=True),
                sa.Column("error_message", sa.Text(), nullable=True),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["parent_host_id"],
                    ["host.id"],
                    ondelete="CASCADE",
                ),
            )
        else:
            op.create_table(
                "reboot_orchestration",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("parent_host_id", sa.String(36), nullable=False),
                sa.Column(
                    "status",
                    sa.String(length=50),
                    nullable=False,
                    server_default="pending_shutdown",
                ),
                sa.Column("child_hosts_snapshot", sa.Text(), nullable=False),
                sa.Column("child_hosts_restart_status", sa.Text(), nullable=True),
                sa.Column(
                    "shutdown_timeout_seconds",
                    sa.Integer(),
                    nullable=False,
                    server_default="120",
                ),
                sa.Column("initiated_by", sa.String(length=255), nullable=False),
                sa.Column("initiated_at", sa.DateTime(), nullable=False),
                sa.Column("shutdown_completed_at", sa.DateTime(), nullable=True),
                sa.Column("reboot_issued_at", sa.DateTime(), nullable=True),
                sa.Column("agent_reconnected_at", sa.DateTime(), nullable=True),
                sa.Column("restart_completed_at", sa.DateTime(), nullable=True),
                sa.Column("error_message", sa.Text(), nullable=True),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["parent_host_id"],
                    ["host.id"],
                    ondelete="CASCADE",
                ),
            )

        op.create_index(
            op.f("ix_reboot_orchestration_parent_host_id"),
            "reboot_orchestration",
            ["parent_host_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_reboot_orchestration_status"),
            "reboot_orchestration",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "reboot_orchestration" in tables:
        op.drop_index(
            op.f("ix_reboot_orchestration_status"),
            table_name="reboot_orchestration",
        )
        op.drop_index(
            op.f("ix_reboot_orchestration_parent_host_id"),
            table_name="reboot_orchestration",
        )
        op.drop_table("reboot_orchestration")
