"""create user_invitation (Phase 13.3 — Administrator Invitations)

Pending admin invitations: an admin invites a person by email with a set of
security roles; the recipient accepts via a one-time tokened link that creates
their user account, assigns the roles, and sets their password.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: h1userinvite
Revises: g1cveshared
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "h1userinvite"
down_revision: Union[str, None] = "g1cveshared"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "user_invitation"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("role_ids", sa.JSON(), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_invitation_email", _TABLE, ["email"])
    op.create_index("ix_user_invitation_token", _TABLE, ["token"], unique=True)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_TABLE)
