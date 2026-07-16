# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_tenant_db_version

Phase 13.1.C: track each tenant DB's current Alembic revision in the
registry (design §12) so migration rollouts can be staged/canaried
tenant-by-tenant.

Third migration in the **registry** chain (chains off ``r2registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod); the one FK
targets ``registry_tenant`` (same partition).

Revision ID: r3registry
Revises: r2registry
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r3registry"
down_revision: Union[str, None] = "r2registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_tenant_db_version"


def _guid_type():
    """UUID-typed column for the live dialect (UUID on PG, String(36) else)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    """Create the tenant-db-version table + index (idempotent)."""
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
            sa.Column("chain", sa.String(32), nullable=False),
            sa.Column("revision", sa.String(64), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "tenant_id", "chain", name="uq_registry_db_version_tenant_chain"
            ),
        )

    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_db_version_tenant" not in existing_indexes:
        op.create_index(
            "ix_registry_db_version_tenant", _TABLE, ["tenant_id"], unique=False
        )


def downgrade() -> None:
    """Drop the tenant-db-version table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_db_version_tenant" in existing_indexes:
        op.drop_index("ix_registry_db_version_tenant", table_name=_TABLE)
    op.drop_table(_TABLE)
