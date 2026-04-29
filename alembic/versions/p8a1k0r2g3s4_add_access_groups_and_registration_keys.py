"""Add access_groups, registration_keys, host_access_groups, user_access_groups (Phase 8.1).

Revision ID: p8a1k0r2g3s4
Revises: 4b3a68c8beee
Create Date: 2026-04-29 09:00:00.000000

Four new tables for the Phase 8.1 access-group hierarchy + registration-
key flow:

  access_groups            tree of organizational scopes; self-FK on parent_id
  registration_keys        pre-shared agent-registration secrets
  host_access_groups       many-to-many: hosts ↔ access groups
  user_access_groups       many-to-many: users ↔ access groups

Schema-only — no data seeding.  The migration is reversible:  downgrade
drops all four tables in dependency order.  Round-trip verified by the
``migration-roundtrip`` job (see scripts/migration_roundtrip.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "p8a1k0r2g3s4"
down_revision: Union[str, None] = "4b3a68c8beee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "parent_id",
            sa.String(length=36),
            sa.ForeignKey("access_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_access_groups_parent_id", "access_groups", ["parent_id"], unique=False
    )
    op.create_index("ix_access_groups_name", "access_groups", ["name"], unique=False)

    op.create_table(
        "registration_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "access_group_id",
            sa.String(length=36),
            sa.ForeignKey("access_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_registration_keys_key", "registration_keys", ["key"], unique=False
    )
    op.create_index(
        "ix_registration_keys_access_group_id",
        "registration_keys",
        ["access_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_registration_keys_revoked",
        "registration_keys",
        ["revoked"],
        unique=False,
    )

    op.create_table(
        "host_access_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "host_id",
            sa.String(length=36),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_group_id",
            sa.String(length=36),
            sa.ForeignKey("access_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_host_access_groups_host_group",
        "host_access_groups",
        ["host_id", "access_group_id"],
        unique=True,
    )

    op.create_table(
        "user_access_groups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "access_group_id",
            sa.String(length=36),
            sa.ForeignKey("access_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_user_access_groups_user_group",
        "user_access_groups",
        ["user_id", "access_group_id"],
        unique=True,
    )


def downgrade() -> None:
    # Drop in reverse dependency order:  m2m tables first, then
    # registration_keys (FK to access_groups), then access_groups itself.
    op.drop_index("ix_user_access_groups_user_group", table_name="user_access_groups")
    op.drop_table("user_access_groups")

    op.drop_index("ix_host_access_groups_host_group", table_name="host_access_groups")
    op.drop_table("host_access_groups")

    op.drop_index("ix_registration_keys_revoked", table_name="registration_keys")
    op.drop_index(
        "ix_registration_keys_access_group_id", table_name="registration_keys"
    )
    op.drop_index("ix_registration_keys_key", table_name="registration_keys")
    op.drop_table("registration_keys")

    op.drop_index("ix_access_groups_name", table_name="access_groups")
    op.drop_index("ix_access_groups_parent_id", table_name="access_groups")
    op.drop_table("access_groups")
