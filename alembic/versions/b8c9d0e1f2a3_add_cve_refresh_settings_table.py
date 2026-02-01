"""add_cve_refresh_settings_table

Revision ID: b8c9d0e1f2a3
Revises: a6b7c8d9e0f1
Create Date: 2026-02-01 12:00:00.000000

This migration adds the cve_refresh_settings table for configuring
automatic CVE database updates from security data sources.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists (idempotency)
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "cve_refresh_settings" not in tables:
        # Determine if we're using PostgreSQL or SQLite
        is_postgresql = conn.dialect.name == "postgresql"

        if is_postgresql:
            # PostgreSQL version with UUID and proper JSON type
            op.create_table(
                "cve_refresh_settings",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column(
                    "refresh_interval_hours",
                    sa.Integer(),
                    nullable=False,
                    server_default="24",
                ),
                sa.Column(
                    "enabled_sources",
                    postgresql.JSON(),
                    nullable=False,
                    server_default='["nvd", "ubuntu", "debian", "redhat"]',
                ),
                sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
                sa.Column("next_refresh_at", sa.DateTime(), nullable=True),
                sa.Column("nvd_api_key", sa.String(length=255), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )
        else:
            # SQLite version with String for UUID and Text for JSON
            op.create_table(
                "cve_refresh_settings",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column(
                    "refresh_interval_hours",
                    sa.Integer(),
                    nullable=False,
                    server_default="24",
                ),
                sa.Column(
                    "enabled_sources",
                    sa.Text(),
                    nullable=False,
                    server_default='["nvd", "ubuntu", "debian", "redhat"]',
                ),
                sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
                sa.Column("next_refresh_at", sa.DateTime(), nullable=True),
                sa.Column("nvd_api_key", sa.String(length=255), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
            )

        # Create index on id for faster lookups
        op.create_index(
            op.f("ix_cve_refresh_settings_id"), "cve_refresh_settings", ["id"], unique=False
        )


def downgrade() -> None:
    # Check if table exists before dropping (idempotency)
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "cve_refresh_settings" in tables:
        # Drop index first
        op.drop_index(op.f("ix_cve_refresh_settings_id"), table_name="cve_refresh_settings")
        # Drop the table
        op.drop_table("cve_refresh_settings")
