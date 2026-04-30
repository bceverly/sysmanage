"""Add report_branding, report_template, dynamic_secret_lease (Phase 8.7).

Revision ID: p8a4r5b6t7l8
Revises: p8a3p4k5g6c7
Create Date: 2026-04-29 14:30:00.000000

Three new tables backing the Pro+ ``reporting_engine`` and
``secrets_engine`` 8.7 enhancements:

  report_branding         singleton: company name + header text + logo path
  report_template         admin-defined custom report layouts
  dynamic_secret_lease    OpenBAO dynamic-secret lease audit + revocation hook

Reversible — downgrade drops the three tables in dependency order.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p8a4r5b6t7l8"
down_revision: Union[str, None] = "p8a3p4k5g6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_branding",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("header_text", sa.String(length=500), nullable=True),
        sa.Column("logo_data", sa.LargeBinary(), nullable=True),
        sa.Column("logo_mime_type", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "updated_by",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "report_template",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_report_type", sa.String(length=50), nullable=False),
        sa.Column("selected_fields", sa.JSON(), nullable=False),
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
    op.create_index(
        "ix_report_template_base_report_type",
        "report_template",
        ["base_report_type"],
    )

    op.create_table(
        "dynamic_secret_lease",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("backend_role", sa.String(length=255), nullable=False),
        sa.Column("vault_lease_id", sa.String(length=500), nullable=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("secret_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "issued_by",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_dynamic_secret_lease_kind", "dynamic_secret_lease", ["kind"])
    op.create_index(
        "ix_dynamic_secret_lease_status", "dynamic_secret_lease", ["status"]
    )
    op.create_index(
        "ix_dynamic_secret_lease_expires_at",
        "dynamic_secret_lease",
        ["expires_at"],
    )
    op.create_index(
        "ix_dynamic_secret_lease_vault_lease_id",
        "dynamic_secret_lease",
        ["vault_lease_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dynamic_secret_lease_vault_lease_id",
        table_name="dynamic_secret_lease",
    )
    op.drop_index(
        "ix_dynamic_secret_lease_expires_at",
        table_name="dynamic_secret_lease",
    )
    op.drop_index("ix_dynamic_secret_lease_status", table_name="dynamic_secret_lease")
    op.drop_index("ix_dynamic_secret_lease_kind", table_name="dynamic_secret_lease")
    op.drop_table("dynamic_secret_lease")

    op.drop_index(
        "ix_report_template_base_report_type", table_name="report_template"
    )
    op.drop_table("report_template")

    op.drop_table("report_branding")
