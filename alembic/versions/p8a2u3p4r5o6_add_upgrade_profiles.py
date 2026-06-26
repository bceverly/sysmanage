"""Add upgrade_profiles (Phase 8.2 — scheduled update profiles).

Revision ID: p8a2u3p4r5o6
Revises: p8a1k0r2g3s4
Create Date: 2026-04-29 10:00:00.000000

One new table:

  upgrade_profiles    cron-driven update plan; tag_id scopes the rollout
                      (NULL = all approved hosts); security_only flag
                      restricts the plan to security updates;
                      staggered_window_min spreads the rollout across N
                      minutes to avoid thundering herd.

Reversible — downgrade drops the table and its indexes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p8a2u3p4r5o6"
down_revision: Union[str, None] = "p8a1k0r2g3s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upgrade_profiles",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cron", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(length=40), nullable=True),
        sa.Column("next_run", sa.DateTime(), nullable=True),
        sa.Column(
            "security_only", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("package_managers", sa.Text(), nullable=True),
        sa.Column(
            "staggered_window_min",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "tag_id",
            sa.UUID(),
            sa.ForeignKey("tags.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        "ix_upgrade_profiles_enabled_next_run",
        "upgrade_profiles",
        ["enabled", "next_run"],
        unique=False,
    )
    op.create_index(
        "ix_upgrade_profiles_tag_id",
        "upgrade_profiles",
        ["tag_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_upgrade_profiles_tag_id", table_name="upgrade_profiles"
    )
    op.drop_index(
        "ix_upgrade_profiles_enabled_next_run", table_name="upgrade_profiles"
    )
    op.drop_table("upgrade_profiles")
