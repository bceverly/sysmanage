# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_enrollment_token

Phase 13.1 (data plane): tenant-scoped agent enrollment tokens.  An admin
generates a token bound to a tenant; an agent presents it at registration to
be enrolled into that tenant.  Only the SHA-256 hash is stored.

Fourth migration in the **registry** chain (chains off ``r3registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod); the one FK
targets ``registry_tenant`` (same partition).

Revision ID: r4registry
Revises: r3registry
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r4registry"
down_revision: Union[str, None] = "r3registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_enrollment_token"


def _guid_type():
    """UUID-typed column for the live dialect (UUID on PG, String(36) else)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    """Create the enrollment-token table + indexes (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()

    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column(
                "tenant_id",
                guid,
                sa.ForeignKey("registry_tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("label", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("use_count", sa.Integer(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_enrollment_token_tenant" not in existing_indexes:
        op.create_index(
            "ix_registry_enrollment_token_tenant", _TABLE, ["tenant_id"], unique=False
        )
    if "ix_registry_enrollment_token_hash" not in existing_indexes:
        op.create_index(
            "ix_registry_enrollment_token_hash", _TABLE, ["token_hash"], unique=False
        )


def downgrade() -> None:
    """Drop the enrollment-token table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name in (
        "ix_registry_enrollment_token_hash",
        "ix_registry_enrollment_token_tenant",
    ):
        if name in existing_indexes:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
