"""add_compliance_tables

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-02-04 14:40:00.000000

This migration adds the compliance_profile and host_compliance_scan
tables for the compliance_engine Pro+ module.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    is_postgresql = conn.dialect.name == "postgresql"

    # --- compliance_profile ---
    if "compliance_profile" not in tables:
        if is_postgresql:
            op.create_table(
                "compliance_profile",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column(
                    "benchmark_type",
                    sa.String(length=50),
                    nullable=False,
                    server_default="CUSTOM",
                ),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="true"
                ),
                sa.Column("rules", postgresql.JSON(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("name"),
            )
        else:
            op.create_table(
                "compliance_profile",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("name", sa.String(length=255), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column(
                    "benchmark_type",
                    sa.String(length=50),
                    nullable=False,
                    server_default="CUSTOM",
                ),
                sa.Column(
                    "enabled", sa.Boolean(), nullable=False, server_default="1"
                ),
                sa.Column("rules", sa.Text(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("updated_at", sa.DateTime(), nullable=False),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("name"),
            )

        op.create_index(
            op.f("ix_compliance_profile_id"),
            "compliance_profile",
            ["id"],
            unique=False,
        )

    # --- host_compliance_scan ---
    if "host_compliance_scan" not in tables:
        if is_postgresql:
            op.create_table(
                "host_compliance_scan",
                sa.Column("id", sa.UUID(), nullable=False),
                sa.Column("host_id", sa.UUID(), nullable=False),
                sa.Column("profile_id", sa.UUID(), nullable=True),
                sa.Column("scanned_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "total_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "passed_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "failed_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "error_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "not_applicable_rules",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "compliance_score",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "compliance_grade",
                    sa.String(length=2),
                    nullable=False,
                    server_default="F",
                ),
                sa.Column(
                    "critical_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "high_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "medium_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "low_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("summary", sa.Text(), nullable=True),
                sa.Column("results", postgresql.JSON(), nullable=True),
                sa.Column(
                    "scanner_version", sa.String(length=20), nullable=True
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["host_id"], ["host.id"], ondelete="CASCADE"
                ),
                sa.ForeignKeyConstraint(
                    ["profile_id"],
                    ["compliance_profile.id"],
                    ondelete="SET NULL",
                ),
            )
        else:
            op.create_table(
                "host_compliance_scan",
                sa.Column("id", sa.String(36), nullable=False),
                sa.Column("host_id", sa.String(36), nullable=False),
                sa.Column("profile_id", sa.String(36), nullable=True),
                sa.Column("scanned_at", sa.DateTime(), nullable=False),
                sa.Column(
                    "total_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "passed_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "failed_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "error_rules", sa.Integer(), nullable=False, server_default="0"
                ),
                sa.Column(
                    "not_applicable_rules",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "compliance_score",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "compliance_grade",
                    sa.String(length=2),
                    nullable=False,
                    server_default="F",
                ),
                sa.Column(
                    "critical_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "high_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "medium_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column(
                    "low_failures",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
                sa.Column("summary", sa.Text(), nullable=True),
                sa.Column("results", sa.Text(), nullable=True),
                sa.Column(
                    "scanner_version", sa.String(length=20), nullable=True
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.ForeignKeyConstraint(
                    ["host_id"], ["host.id"], ondelete="CASCADE"
                ),
                sa.ForeignKeyConstraint(
                    ["profile_id"],
                    ["compliance_profile.id"],
                    ondelete="SET NULL",
                ),
            )

        op.create_index(
            op.f("ix_host_compliance_scan_id"),
            "host_compliance_scan",
            ["id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_host_compliance_scan_host_id"),
            "host_compliance_scan",
            ["host_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_host_compliance_scan_profile_id"),
            "host_compliance_scan",
            ["profile_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_host_compliance_scan_scanned_at"),
            "host_compliance_scan",
            ["scanned_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if "host_compliance_scan" in tables:
        op.drop_index(
            op.f("ix_host_compliance_scan_scanned_at"),
            table_name="host_compliance_scan",
        )
        op.drop_index(
            op.f("ix_host_compliance_scan_profile_id"),
            table_name="host_compliance_scan",
        )
        op.drop_index(
            op.f("ix_host_compliance_scan_host_id"),
            table_name="host_compliance_scan",
        )
        op.drop_index(
            op.f("ix_host_compliance_scan_id"),
            table_name="host_compliance_scan",
        )
        op.drop_table("host_compliance_scan")

    if "compliance_profile" in tables:
        op.drop_index(
            op.f("ix_compliance_profile_id"),
            table_name="compliance_profile",
        )
        op.drop_table("compliance_profile")
