# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_host_tenant_updated_at

Phase 22 (multi-tenant scale): ``registry_host_tenant.updated_at`` (indexed),
set whenever a host is bound or re-bound.  Each server worker caches host ->
tenant bindings and asks every few seconds which bindings changed since it
last asked, so a host moved to another tenant is re-routed at once while the
cache serves every other lookup.  Existing rows take their ``created_at``.

Tenth migration in the **registry** chain (chains off ``r9registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod).

Revision ID: r10registry
Revises: r9registry
Create Date: 2026-10-04
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "r10registry"
down_revision: Union[str, None] = "r9registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_host_tenant"
_COLUMN = "updated_at"
_INDEX = "ix_registry_host_tenant_updated"


def upgrade() -> None:
    """Add the column (backfilled from created_at) and its index (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))
    op.execute(
        sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = created_at WHERE {_COLUMN} IS NULL")
    )
    existing = {idx["name"] for idx in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in existing:
        op.create_index(_INDEX, _TABLE, [_COLUMN], unique=False)


def downgrade() -> None:
    """Drop the index and the column (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    if _INDEX in {idx["name"] for idx in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in {col["name"] for col in inspector.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
