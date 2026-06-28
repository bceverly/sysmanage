"""add api_key table (Phase 13.2 — API Completeness)

Backs the ``ApiKey`` model: long-lived, hashed credentials that let automation
authenticate to the REST API as a user (alternative to an interactive JWT).

Only the SHA-256 digest of the key is stored (``key_hash``, unique) plus a
non-secret display prefix (``key_prefix``); the plaintext is shown once at
creation and never persisted.  ``user_id`` FKs ``user.id`` with ON DELETE
CASCADE.  ``tenant_id`` is a soft reference to ``registry_tenant.id`` (no
cross-partition FK) for optional per-tenant pinning.

Idempotent (``inspect().has_table`` guard) and SQLite + PostgreSQL safe.
Chains off ``e4scimprovider``.

Revision ID: f1apikey01
Revises: e4scimprovider
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "f1apikey01"
down_revision: Union[str, None] = "e4scimprovider"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("api_key"):
        op.create_table(
            "api_key",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "user_id",
                GUID(),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("key_prefix", sa.String(length=32), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("scopes", sa.Text(), nullable=True),
            sa.Column("tenant_id", GUID(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
        )
        # Indexes are created here (inside the table-create guard) so the whole
        # migration is idempotent: when the table already exists we skip both.
        op.create_index("ix_api_key_user_id", "api_key", ["user_id"])
        op.create_index("ix_api_key_key_prefix", "api_key", ["key_prefix"])
        op.create_index("ix_api_key_key_hash", "api_key", ["key_hash"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if insp.has_table("api_key"):
        op.drop_table("api_key")
