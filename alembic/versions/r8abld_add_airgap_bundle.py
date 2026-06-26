"""Add airgap_bundle table — multi-OS air-gap install ISO builder.

Revision ID: r8abld
Revises: r7hardening
Create Date: 2026-05-24 10:00:00.000000

One new table:

  airgap_bundle    one row per ISO build job kicked off by the
                   "Air-Gap Bundles" Settings tab.  Tracks the build
                   subprocess's lifecycle (queued -> building -> ready
                   | failed), where the resulting ISO lives on disk,
                   and which user triggered it.

Reversible — downgrade drops the table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r8abld"
down_revision: Union[str, None] = "r7hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "airgap_bundle",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_airgap_bundle_product", "airgap_bundle", ["product"], unique=False
    )
    op.create_index(
        "ix_airgap_bundle_status", "airgap_bundle", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_airgap_bundle_status", table_name="airgap_bundle")
    op.drop_index("ix_airgap_bundle_product", table_name="airgap_bundle")
    op.drop_table("airgap_bundle")
