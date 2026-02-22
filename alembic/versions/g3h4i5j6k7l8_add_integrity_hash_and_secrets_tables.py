"""add_integrity_hash_and_secrets_tables

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-02-13 12:00:00.000000

Adds integrity_hash column to audit_log, and creates the secret_version
and rotation_schedule tables for Phase 2 Pro+ features.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    is_postgresql = conn.dialect.name == "postgresql"

    # --- Add integrity_hash column to audit_log ---
    if "audit_log" in tables:
        columns = [col["name"] for col in inspector.get_columns("audit_log")]
        if "integrity_hash" not in columns:
            op.add_column(
                "audit_log",
                sa.Column("integrity_hash", sa.String(64), nullable=True),
            )

    # --- secret_version ---
    if "secret_version" not in tables:
        if is_postgresql:
            op.create_table(
                "secret_version",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("secret_id", sa.UUID(), nullable=False),
                sa.Column("version_number", sa.Integer(), nullable=False),
                sa.Column("content_hash", sa.String(length=64), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=True),
                sa.Column("created_by", sa.String(length=255), nullable=True),
                sa.Column(
                    "change_description", sa.String(length=500), nullable=True
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["secret_id"],
                    ["secrets.id"],
                    ondelete="CASCADE",
                ),
            )
        else:
            op.create_table(
                "secret_version",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("secret_id", sa.String(36), nullable=False),
                sa.Column("version_number", sa.Integer(), nullable=False),
                sa.Column("content_hash", sa.String(length=64), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=True),
                sa.Column("created_by", sa.String(length=255), nullable=True),
                sa.Column(
                    "change_description", sa.String(length=500), nullable=True
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["secret_id"],
                    ["secrets.id"],
                    ondelete="CASCADE",
                ),
            )

        op.create_index(
            op.f("ix_secret_version_secret_id_version"),
            "secret_version",
            ["secret_id", "version_number"],
            unique=True,
        )

    # --- rotation_schedule ---
    if "rotation_schedule" not in tables:
        if is_postgresql:
            op.create_table(
                "rotation_schedule",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("secret_id", sa.UUID(), nullable=False),
                sa.Column(
                    "frequency", sa.String(length=20), nullable=False
                ),
                sa.Column(
                    "notify_days_before",
                    sa.Integer(),
                    nullable=False,
                    server_default="7",
                ),
                sa.Column(
                    "auto_rotate",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                ),
                sa.Column(
                    "enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default="true",
                ),
                sa.Column("next_rotation", sa.DateTime(), nullable=True),
                sa.Column("last_rotation", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["secret_id"],
                    ["secrets.id"],
                    ondelete="CASCADE",
                ),
            )
        else:
            op.create_table(
                "rotation_schedule",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("secret_id", sa.String(36), nullable=False),
                sa.Column(
                    "frequency", sa.String(length=20), nullable=False
                ),
                sa.Column(
                    "notify_days_before",
                    sa.Integer(),
                    nullable=False,
                    server_default="7",
                ),
                sa.Column(
                    "auto_rotate",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "enabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default="1",
                ),
                sa.Column("next_rotation", sa.DateTime(), nullable=True),
                sa.Column("last_rotation", sa.DateTime(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["secret_id"],
                    ["secrets.id"],
                    ondelete="CASCADE",
                ),
            )

        op.create_index(
            op.f("ix_rotation_schedule_secret_id"),
            "rotation_schedule",
            ["secret_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "rotation_schedule" in tables:
        op.drop_index(
            op.f("ix_rotation_schedule_secret_id"),
            table_name="rotation_schedule",
        )
        op.drop_table("rotation_schedule")

    if "secret_version" in tables:
        op.drop_index(
            op.f("ix_secret_version_secret_id_version"),
            table_name="secret_version",
        )
        op.drop_table("secret_version")

    if "audit_log" in tables:
        columns = [col["name"] for col in inspector.get_columns("audit_log")]
        if "integrity_hash" in columns:
            op.drop_column("audit_log", "integrity_hash")
