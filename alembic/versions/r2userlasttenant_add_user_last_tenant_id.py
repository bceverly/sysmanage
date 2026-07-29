# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add user.last_tenant_id — sticky last-selected tenant (Phase 13 convenience)

A SOFT reference to ``registry_tenant.id`` (cross-partition — no FK) on the
server-global ``user`` table.  Written when a user switches tenants and
populated on first login, so a multi-tenant user lands back in the tenant they
usually work in.  NULL for single-tenant / non-multi-tenant users.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r2userlasttenant
Revises: r1provisioning
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "r2userlasttenant"
down_revision: Union[str, None] = "r1provisioning"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "user"
_COLUMN = "last_tenant_id"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        # GUID renders as CHAR(36)/native UUID; a plain 36-char string column is
        # the SQLite+PostgreSQL-portable shape (matches other GUID soft refs).
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=36), nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
