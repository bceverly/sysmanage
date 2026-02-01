"""Add Pro+ license and health analysis tables

Revision ID: a0b1c2d3e4f5
Revises: j5k6l7m8n9o0
Create Date: 2026-01-31 10:00:00.000000

This migration adds tables for Pro+ license management, module caching,
and AI-powered host health analysis.

Tables added:
- proplus_license: Stores validated Pro+ license information
- proplus_license_validation_log: Audit log for license validation attempts
- proplus_module_cache: Cache of downloaded Cython modules
- host_health_analysis: AI health analysis results for hosts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "j5k6l7m8n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Pro+ tables."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Use appropriate UUID type based on database
    if is_sqlite:
        uuid_type = sa.String(36)
        json_type = sa.Text()
    else:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSON()

    # Create proplus_license table
    op.create_table(
        "proplus_license",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("license_key_hash", sa.String(128), nullable=False),
        sa.Column("license_id", sa.String(36), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("features", json_type, nullable=False),
        sa.Column("modules", json_type, nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("offline_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("last_phone_home_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_id"),
    )
    op.create_index("ix_proplus_license_id", "proplus_license", ["id"])
    op.create_index("ix_proplus_license_license_id", "proplus_license", ["license_id"])

    # Create proplus_license_validation_log table
    op.create_table(
        "proplus_license_validation_log",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("license_id", sa.String(36), nullable=True),
        sa.Column("validation_type", sa.String(50), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", json_type, nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proplus_license_validation_log_id",
        "proplus_license_validation_log",
        ["id"],
    )
    op.create_index(
        "ix_proplus_license_validation_log_license_id",
        "proplus_license_validation_log",
        ["license_id"],
    )
    op.create_index(
        "ix_proplus_license_validation_log_validated_at",
        "proplus_license_validation_log",
        ["validated_at"],
    )

    # Create proplus_module_cache table
    op.create_table(
        "proplus_module_cache",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("module_code", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("architecture", sa.String(20), nullable=False),
        sa.Column("python_version", sa.String(10), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_hash", sa.String(128), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "module_code",
            "version",
            "platform",
            "architecture",
            "python_version",
            name="uq_proplus_module_cache_unique",
        ),
    )
    op.create_index("ix_proplus_module_cache_id", "proplus_module_cache", ["id"])
    op.create_index(
        "ix_proplus_module_cache_module_code", "proplus_module_cache", ["module_code"]
    )

    # Create host_health_analysis table
    op.create_table(
        "host_health_analysis",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("host_id", uuid_type, nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("issues", json_type, nullable=True),
        sa.Column("recommendations", json_type, nullable=True),
        sa.Column("analysis_version", sa.String(20), nullable=True),
        sa.Column("raw_metrics", json_type, nullable=True),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["host.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_host_health_analysis_id", "host_health_analysis", ["id"])
    op.create_index(
        "ix_host_health_analysis_host_id", "host_health_analysis", ["host_id"]
    )
    op.create_index(
        "ix_host_health_analysis_analyzed_at", "host_health_analysis", ["analyzed_at"]
    )


def downgrade() -> None:
    """Drop Pro+ tables."""
    op.drop_table("host_health_analysis")
    op.drop_table("proplus_module_cache")
    op.drop_table("proplus_license_validation_log")
    op.drop_table("proplus_license")
