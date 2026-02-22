"""add_scheduled_report_and_retention_tables

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-02-12 12:00:00.000000

Adds the scheduled_report, scheduled_report_channel, audit_retention_policy,
and audit_log_archive tables for Phase 2 Pro+ features.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    is_postgresql = conn.dialect.name == "postgresql"

    # --- scheduled_report ---
    if "scheduled_report" not in tables:
        if is_postgresql:
            op.create_table(
                "scheduled_report",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("report_type", sa.String(length=50), nullable=False),
                sa.Column("schedule_type", sa.String(length=20), nullable=False),
                sa.Column("schedule_config", postgresql.JSON(), nullable=False),
                sa.Column(
                    "output_format",
                    sa.String(length=10),
                    nullable=False,
                    server_default="pdf",
                ),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column("last_run_at", sa.DateTime(), nullable=True),
                sa.Column("next_run_at", sa.DateTime(), nullable=True),
                sa.Column("created_by", sa.String(length=255), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )
        else:
            op.create_table(
                "scheduled_report",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("report_type", sa.String(length=50), nullable=False),
                sa.Column("schedule_type", sa.String(length=20), nullable=False),
                sa.Column("schedule_config", sa.Text(), nullable=False),
                sa.Column(
                    "output_format",
                    sa.String(length=10),
                    nullable=False,
                    server_default="pdf",
                ),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column("last_run_at", sa.DateTime(), nullable=True),
                sa.Column("next_run_at", sa.DateTime(), nullable=True),
                sa.Column("created_by", sa.String(length=255), nullable=False),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )

    # --- scheduled_report_channel ---
    if "scheduled_report_channel" not in tables:
        if is_postgresql:
            op.create_table(
                "scheduled_report_channel",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("scheduled_report_id", sa.UUID(), nullable=False),
                sa.Column("channel_id", sa.UUID(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["scheduled_report_id"],
                    ["scheduled_report.id"],
                    ondelete="CASCADE",
                ),
                sa.ForeignKeyConstraint(
                    ["channel_id"],
                    ["notification_channel.id"],
                    ondelete="CASCADE",
                ),
            )
        else:
            op.create_table(
                "scheduled_report_channel",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("scheduled_report_id", sa.String(36), nullable=False),
                sa.Column("channel_id", sa.String(36), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["scheduled_report_id"],
                    ["scheduled_report.id"],
                    ondelete="CASCADE",
                ),
                sa.ForeignKeyConstraint(
                    ["channel_id"],
                    ["notification_channel.id"],
                    ondelete="CASCADE",
                ),
            )

        op.create_index(
            op.f("ix_scheduled_report_channel_report_id"),
            "scheduled_report_channel",
            ["scheduled_report_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_scheduled_report_channel_channel_id"),
            "scheduled_report_channel",
            ["channel_id"],
            unique=False,
        )

    # --- audit_retention_policy ---
    if "audit_retention_policy" not in tables:
        if is_postgresql:
            op.create_table(
                "audit_retention_policy",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("retention_days", sa.Integer(), nullable=False),
                sa.Column("action", sa.String(length=20), nullable=False),
                sa.Column("entity_types", postgresql.JSON(), nullable=True),
                sa.Column("action_types", postgresql.JSON(), nullable=True),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column("last_run_at", sa.DateTime(), nullable=True),
                sa.Column("next_run_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "entries_processed",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )
        else:
            op.create_table(
                "audit_retention_policy",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("retention_days", sa.Integer(), nullable=False),
                sa.Column("action", sa.String(length=20), nullable=False),
                sa.Column("entity_types", sa.Text(), nullable=True),
                sa.Column("action_types", sa.Text(), nullable=True),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column("last_run_at", sa.DateTime(), nullable=True),
                sa.Column("next_run_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "entries_processed",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )

    # --- audit_log_archive ---
    if "audit_log_archive" not in tables:
        if is_postgresql:
            op.create_table(
                "audit_log_archive",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("timestamp", sa.DateTime(), nullable=False),
                sa.Column("user_id", sa.UUID(), nullable=True),
                sa.Column("username", sa.String(length=255), nullable=True),
                sa.Column("action_type", sa.String(length=50), nullable=False),
                sa.Column("entity_type", sa.String(length=100), nullable=False),
                sa.Column("entity_id", sa.String(length=255), nullable=True),
                sa.Column("entity_name", sa.String(length=255), nullable=True),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("details", postgresql.JSON(), nullable=True),
                sa.Column("ip_address", sa.String(length=45), nullable=True),
                sa.Column("user_agent", sa.String(length=500), nullable=True),
                sa.Column("result", sa.String(length=20), nullable=False),
                sa.Column("error_message", sa.Text(), nullable=True),
                sa.Column("category", sa.String(length=50), nullable=True),
                sa.Column("entry_type", sa.String(length=50), nullable=True),
                sa.Column("archived_at", sa.DateTime(), nullable=False),
                sa.Column("archived_by_policy_id", sa.UUID(), nullable=True),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["archived_by_policy_id"],
                    ["audit_retention_policy.id"],
                    ondelete="SET NULL",
                ),
            )
        else:
            op.create_table(
                "audit_log_archive",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("timestamp", sa.DateTime(), nullable=False),
                sa.Column("user_id", sa.String(36), nullable=True),
                sa.Column("username", sa.String(length=255), nullable=True),
                sa.Column("action_type", sa.String(length=50), nullable=False),
                sa.Column("entity_type", sa.String(length=100), nullable=False),
                sa.Column("entity_id", sa.String(length=255), nullable=True),
                sa.Column("entity_name", sa.String(length=255), nullable=True),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("details", sa.Text(), nullable=True),
                sa.Column("ip_address", sa.String(length=45), nullable=True),
                sa.Column("user_agent", sa.String(length=500), nullable=True),
                sa.Column("result", sa.String(length=20), nullable=False),
                sa.Column("error_message", sa.Text(), nullable=True),
                sa.Column("category", sa.String(length=50), nullable=True),
                sa.Column("entry_type", sa.String(length=50), nullable=True),
                sa.Column("archived_at", sa.DateTime(), nullable=False),
                sa.Column("archived_by_policy_id", sa.String(36), nullable=True),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["archived_by_policy_id"],
                    ["audit_retention_policy.id"],
                    ondelete="SET NULL",
                ),
            )

        op.create_index(
            op.f("ix_audit_log_archive_timestamp"),
            "audit_log_archive",
            ["timestamp"],
            unique=False,
        )
        op.create_index(
            op.f("ix_audit_log_archive_user_id"),
            "audit_log_archive",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_audit_log_archive_action_type"),
            "audit_log_archive",
            ["action_type"],
            unique=False,
        )
        op.create_index(
            op.f("ix_audit_log_archive_entity_type"),
            "audit_log_archive",
            ["entity_type"],
            unique=False,
        )
        op.create_index(
            op.f("ix_audit_log_archive_category"),
            "audit_log_archive",
            ["category"],
            unique=False,
        )
        op.create_index(
            op.f("ix_audit_log_archive_entry_type"),
            "audit_log_archive",
            ["entry_type"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "audit_log_archive" in tables:
        op.drop_index(
            op.f("ix_audit_log_archive_entry_type"),
            table_name="audit_log_archive",
        )
        op.drop_index(
            op.f("ix_audit_log_archive_category"),
            table_name="audit_log_archive",
        )
        op.drop_index(
            op.f("ix_audit_log_archive_entity_type"),
            table_name="audit_log_archive",
        )
        op.drop_index(
            op.f("ix_audit_log_archive_action_type"),
            table_name="audit_log_archive",
        )
        op.drop_index(
            op.f("ix_audit_log_archive_user_id"),
            table_name="audit_log_archive",
        )
        op.drop_index(
            op.f("ix_audit_log_archive_timestamp"),
            table_name="audit_log_archive",
        )
        op.drop_table("audit_log_archive")

    if "audit_retention_policy" in tables:
        op.drop_table("audit_retention_policy")

    if "scheduled_report_channel" in tables:
        op.drop_index(
            op.f("ix_scheduled_report_channel_channel_id"),
            table_name="scheduled_report_channel",
        )
        op.drop_index(
            op.f("ix_scheduled_report_channel_report_id"),
            table_name="scheduled_report_channel",
        )
        op.drop_table("scheduled_report_channel")

    if "scheduled_report" in tables:
        op.drop_table("scheduled_report")
