# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_tenant_edition

Phase 13.1.J (per-tenant edition): each tenant is independently assigned a
``community`` | ``professional`` | ``enterprise`` feature surface from the
control plane.  Module/feature gating resolves against the TENANT's edition (via
the active-tenant context) rather than one global license tier.  Only the column
is OSS; the resolution + Platform-Operator authorization logic lives in the
licensed ``multitenancy_engine``.

Defaults to ``enterprise`` (``server_default``) so every tenant that existed
before this migration keeps the exact behaviour it had — the GA assumption was
that every tenant runs Enterprise, and this preserves it on upgrade.

Sixth migration in the **registry** chain (chains off ``r5registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod).

Revision ID: r6registry
Revises: r5registry
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r6registry"
down_revision: Union[str, None] = "r5registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_tenant"
_COLUMN = "edition"


def upgrade() -> None:
    """Add ``registry_tenant.edition`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return  # registry schema not present (e.g. shared/tenant-only run)
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(32),
                nullable=False,
                server_default="enterprise",
            ),
        )


def downgrade() -> None:
    """Drop ``registry_tenant.edition`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
