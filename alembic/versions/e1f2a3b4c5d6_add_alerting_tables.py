"""add_alerting_tables

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-02-05 12:00:00.000000

Adds the notification_channel, alert_rule, alert_rule_notification_channel,
and alert tables for the alerting_engine Pro+ module.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    is_postgresql = conn.dialect.name == "postgresql"

    # --- notification_channel ---
    if "notification_channel" not in tables:
        if is_postgresql:
            op.create_table(
                "notification_channel",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("channel_type", sa.String(length=50), nullable=False),
                sa.Column("config", postgresql.JSON(), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )
        else:
            op.create_table(
                "notification_channel",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("channel_type", sa.String(length=50), nullable=False),
                sa.Column("config", sa.Text(), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )

        # Note: Primary keys already have implicit indexes, no need to create explicit index on id

    # --- alert_rule ---
    if "alert_rule" not in tables:
        if is_postgresql:
            op.create_table(
                "alert_rule",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("condition_type", sa.String(length=50), nullable=False),
                sa.Column("condition_params", postgresql.JSON(), nullable=False),
                sa.Column("severity", sa.String(length=20), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column(
                    "cooldown_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="60",
                ),
                sa.Column("host_filter", postgresql.JSON(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )
        else:
            op.create_table(
                "alert_rule",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("condition_type", sa.String(length=50), nullable=False),
                sa.Column("condition_params", sa.Text(), nullable=False),
                sa.Column("severity", sa.String(length=20), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column(
                    "cooldown_minutes",
                    sa.Integer(),
                    nullable=False,
                    server_default="60",
                ),
                sa.Column("host_filter", sa.Text(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )

        # Note: Primary keys already have implicit indexes, no need to create explicit index on id

    # --- alert_rule_notification_channel ---
    if "alert_rule_notification_channel" not in tables:
        if is_postgresql:
            op.create_table(
                "alert_rule_notification_channel",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("rule_id", sa.UUID(), nullable=False),
                sa.Column("channel_id", sa.UUID(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["rule_id"], ["alert_rule.id"], ondelete="CASCADE"
                ),
                sa.ForeignKeyConstraint(
                    ["channel_id"],
                    ["notification_channel.id"],
                    ondelete="CASCADE",
                ),
            )
        else:
            op.create_table(
                "alert_rule_notification_channel",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("rule_id", sa.String(36), nullable=False),
                sa.Column("channel_id", sa.String(36), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["rule_id"], ["alert_rule.id"], ondelete="CASCADE"
                ),
                sa.ForeignKeyConstraint(
                    ["channel_id"],
                    ["notification_channel.id"],
                    ondelete="CASCADE",
                ),
            )

        # Note: Primary keys already have implicit indexes, no need to create explicit index on id
        op.create_index(
            op.f("ix_alert_rule_notification_channel_rule_id"),
            "alert_rule_notification_channel",
            ["rule_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_alert_rule_notification_channel_channel_id"),
            "alert_rule_notification_channel",
            ["channel_id"],
            unique=False,
        )

    # --- alert ---
    if "alert" not in tables:
        if is_postgresql:
            op.create_table(
                "alert",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("rule_id", sa.UUID(), nullable=True),
                sa.Column("host_id", sa.UUID(), nullable=False),
                sa.Column("severity", sa.String(length=20), nullable=False),
                sa.Column("title", sa.String(length=500), nullable=False),
                sa.Column("message", sa.Text(), nullable=False),
                sa.Column("details", postgresql.JSON(), nullable=True),
                sa.Column("triggered_at", sa.DateTime(), nullable=False),
                sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "acknowledged_by", sa.String(length=255), nullable=True
                ),
                sa.Column("resolved_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "notification_sent",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["rule_id"], ["alert_rule.id"], ondelete="SET NULL"
                ),
                sa.ForeignKeyConstraint(
                    ["host_id"], ["host.id"], ondelete="CASCADE"
                ),
            )
        else:
            op.create_table(
                "alert",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("rule_id", sa.String(36), nullable=True),
                sa.Column("host_id", sa.String(36), nullable=False),
                sa.Column("severity", sa.String(length=20), nullable=False),
                sa.Column("title", sa.String(length=500), nullable=False),
                sa.Column("message", sa.Text(), nullable=False),
                sa.Column("details", sa.Text(), nullable=True),
                sa.Column("triggered_at", sa.DateTime(), nullable=False),
                sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "acknowledged_by", sa.String(length=255), nullable=True
                ),
                sa.Column("resolved_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "notification_sent",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["rule_id"], ["alert_rule.id"], ondelete="SET NULL"
                ),
                sa.ForeignKeyConstraint(
                    ["host_id"], ["host.id"], ondelete="CASCADE"
                ),
            )

        # Note: Primary keys already have implicit indexes, no need to create explicit index on id
        op.create_index(
            op.f("ix_alert_rule_id_fk"),
            "alert",
            ["rule_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_alert_host_id"),
            "alert",
            ["host_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_alert_triggered_at"),
            "alert",
            ["triggered_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "alert" in tables:
        op.drop_index(op.f("ix_alert_triggered_at"), table_name="alert")
        op.drop_index(op.f("ix_alert_host_id"), table_name="alert")
        op.drop_index(op.f("ix_alert_rule_id_fk"), table_name="alert")
        op.drop_table("alert")

    if "alert_rule_notification_channel" in tables:
        op.drop_index(
            op.f("ix_alert_rule_notification_channel_channel_id"),
            table_name="alert_rule_notification_channel",
        )
        op.drop_index(
            op.f("ix_alert_rule_notification_channel_rule_id"),
            table_name="alert_rule_notification_channel",
        )
        op.drop_table("alert_rule_notification_channel")

    if "alert_rule" in tables:
        op.drop_table("alert_rule")

    if "notification_channel" in tables:
        op.drop_table("notification_channel")
