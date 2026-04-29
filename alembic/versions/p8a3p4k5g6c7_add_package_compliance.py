"""Add package_profiles, package_profile_constraints, host_package_compliance_status (Phase 8.3).

Revision ID: p8a3p4k5g6c7
Revises: p8a2u3p4r5o6
Create Date: 2026-04-29 11:00:00.000000

Three new tables:

  package_profiles                       named profile (e.g., "prod-required")
  package_profile_constraints            REQUIRED/BLOCKED rules with version constraints
  host_package_compliance_status         per-(host, profile) latest scan result

Reversible — downgrade drops the three tables in dependency order.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p8a3p4k5g6c7"
down_revision: Union[str, None] = "p8a2u3p4r5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "package_profiles",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "package_profile_constraints",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.UUID(),
            sa.ForeignKey("package_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("package_manager", sa.String(length=60), nullable=True),
        sa.Column(
            "constraint_type",
            sa.String(length=20),
            nullable=False,
            server_default="REQUIRED",
        ),
        sa.Column("version_op", sa.String(length=4), nullable=True),
        sa.Column("version", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_package_profile_constraints_profile_id",
        "package_profile_constraints",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_package_profile_constraints_package_name",
        "package_profile_constraints",
        ["package_name"],
        unique=False,
    )

    op.create_table(
        "host_package_compliance_status",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "host_id",
            sa.UUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.UUID(),
            sa.ForeignKey("package_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("violations", sa.JSON(), nullable=True),
        sa.Column("last_scan_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_host_package_compliance_host_profile",
        "host_package_compliance_status",
        ["host_id", "profile_id"],
        unique=True,
    )
    op.create_index(
        "ix_host_package_compliance_status",
        "host_package_compliance_status",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_host_package_compliance_status",
        table_name="host_package_compliance_status",
    )
    op.drop_index(
        "ix_host_package_compliance_host_profile",
        table_name="host_package_compliance_status",
    )
    op.drop_table("host_package_compliance_status")

    op.drop_index(
        "ix_package_profile_constraints_package_name",
        table_name="package_profile_constraints",
    )
    op.drop_index(
        "ix_package_profile_constraints_profile_id",
        table_name="package_profile_constraints",
    )
    op.drop_table("package_profile_constraints")

    op.drop_table("package_profiles")
