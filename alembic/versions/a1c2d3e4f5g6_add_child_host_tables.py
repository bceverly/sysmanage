"""add_child_host_tables

Revision ID: a1c2d3e4f5g6
Revises: 826d330052cc
Create Date: 2025-12-01 10:00:00.000000

This migration adds the host_child and child_host_distribution tables
for managing virtual machines and child hosts (WSL, LXD, etc.).

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f5g6"
down_revision: Union[str, None] = "826d330052cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add host_child and child_host_distribution tables."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # Create host_child table
    if "host_child" not in tables:
        op.create_table(
            "host_child",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("parent_host_id", GUID(), nullable=False),
            sa.Column("child_host_id", GUID(), nullable=True),
            # Child host identification
            sa.Column("child_name", sa.String(255), nullable=False),
            sa.Column("child_type", sa.String(50), nullable=False),
            # Distribution/OS info
            sa.Column("distribution", sa.String(100), nullable=True),
            sa.Column("distribution_version", sa.String(50), nullable=True),
            # Configuration
            sa.Column("install_path", sa.String(500), nullable=True),
            sa.Column("default_username", sa.String(100), nullable=True),
            sa.Column("hostname", sa.String(255), nullable=True),
            # State tracking
            sa.Column(
                "status",
                sa.String(50),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("installation_step", sa.String(100), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("installed_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["parent_host_id"], ["host.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["child_host_id"], ["host.id"], ondelete="SET NULL"
            ),
            sa.UniqueConstraint(
                "parent_host_id",
                "child_name",
                "child_type",
                name="uq_host_child_parent_name_type",
            ),
        )

        # Create indexes
        op.create_index(
            "idx_host_child_parent", "host_child", ["parent_host_id"]
        )
        op.create_index("idx_host_child_child", "host_child", ["child_host_id"])
        op.create_index("idx_host_child_status", "host_child", ["status"])

    # Create child_host_distribution table
    if "child_host_distribution" not in tables:
        op.create_table(
            "child_host_distribution",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("child_type", sa.String(50), nullable=False),
            sa.Column("distribution_name", sa.String(100), nullable=False),
            sa.Column("distribution_version", sa.String(50), nullable=False),
            sa.Column("display_name", sa.String(200), nullable=False),
            # Installation details
            sa.Column("install_identifier", sa.String(200), nullable=True),
            sa.Column("executable_name", sa.String(100), nullable=True),
            # Agent installation
            sa.Column("agent_install_method", sa.String(50), nullable=True),
            sa.Column("agent_install_commands", sa.Text(), nullable=True),
            # Metadata
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default="true"
            ),
            sa.Column("min_agent_version", sa.String(20), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Constraints
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "child_type",
                "distribution_name",
                "distribution_version",
                name="uq_child_host_dist_type_name_version",
            ),
        )

        # Create index for child_type lookups
        op.create_index(
            "idx_child_host_dist_type",
            "child_host_distribution",
            ["child_type"],
        )


def downgrade() -> None:
    """Remove host_child and child_host_distribution tables."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # Drop indexes and host_child table
    if "host_child" in tables:
        op.drop_index("idx_host_child_status", table_name="host_child")
        op.drop_index("idx_host_child_child", table_name="host_child")
        op.drop_index("idx_host_child_parent", table_name="host_child")
        op.drop_table("host_child")

    # Drop index and child_host_distribution table
    if "child_host_distribution" in tables:
        op.drop_index(
            "idx_child_host_dist_type", table_name="child_host_distribution"
        )
        op.drop_table("child_host_distribution")
