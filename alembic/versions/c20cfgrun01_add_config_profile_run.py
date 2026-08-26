# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add config_profile_run for Phase 20.1 results + idempotency reporting.

Expand-only: a new table with no changes to existing ones, so an older server
running against this schema is unaffected.

Revision ID: c20cfgrun01
Revises: x4instwhy
Create Date: 2026-08-26
"""

import sqlalchemy as sa

from alembic import op
from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision = "c20cfgrun01"
down_revision = "x4instwhy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the config_profile_run table."""
    op.create_table(
        "config_profile_run",
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("command_id", sa.String(36), nullable=True),
        sa.Column("profile_id", GUID(), nullable=True),
        sa.Column("profile_name", sa.String(255), nullable=True),
        sa.Column("executor", sa.String(50), nullable=True),
        sa.Column(
            "check_mode", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("tasks_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "tasks_unreachable", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("task_detail", sa.Text(), nullable=True),
        sa.Column("error_output", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_config_profile_run_command_id", "config_profile_run", ["command_id"]
    )
    op.create_index(
        "ix_config_profile_run_profile_id", "config_profile_run", ["profile_id"]
    )
    # The dominant query is "this host's recent runs, newest first"; without
    # this it is a full scan of every run ever recorded.
    op.create_index(
        "ix_config_profile_run_host_completed",
        "config_profile_run",
        ["host_id", "completed_at"],
    )


def downgrade() -> None:
    """Drop the config_profile_run table."""
    op.drop_index("ix_config_profile_run_host_completed", "config_profile_run")
    op.drop_index("ix_config_profile_run_profile_id", "config_profile_run")
    op.drop_index("ix_config_profile_run_command_id", "config_profile_run")
    op.drop_table("config_profile_run")
