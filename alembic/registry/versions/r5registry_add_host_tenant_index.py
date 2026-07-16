# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_host_tenant_index

Phase 13.1 (data plane): the server-global host→tenant index.  Lets the
websocket / queue processors resolve which tenant database a host's operations
belong to (populated at enrollment).

Fifth migration in the **registry** chain (chains off ``r4registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod).

Revision ID: r5registry
Revises: r4registry
Create Date: 2026-06-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r5registry"
down_revision: Union[str, None] = "r4registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_host_tenant"


def _guid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    """Create the host→tenant index table + indexes (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    guid = _guid_type()

    if _TABLE not in set(inspector.get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", guid, primary_key=True),
            sa.Column("host_id", guid, nullable=False, unique=True),
            sa.Column(
                "tenant_id",
                guid,
                sa.ForeignKey("registry_tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    if "ix_registry_host_tenant_host" not in existing:
        op.create_index(
            "ix_registry_host_tenant_host", _TABLE, ["host_id"], unique=False
        )
    if "ix_registry_host_tenant_tenant" not in existing:
        op.create_index(
            "ix_registry_host_tenant_tenant", _TABLE, ["tenant_id"], unique=False
        )


def downgrade() -> None:
    """Drop the host→tenant index table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name in ("ix_registry_host_tenant_tenant", "ix_registry_host_tenant_host"):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
