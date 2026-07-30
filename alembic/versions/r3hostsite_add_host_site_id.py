# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host.site_id — federation site placement (Phase 18.1 S4 auto-enroll)

A SOFT reference to ``federation_sites.id`` (coordinator-scoped — no
cross-partition FK) on the ``host`` table (tenant partition + bootstrap DB).
Set at registration when an enrollment token carries a site; NULL otherwise.
There was no local host->site binding before this.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r3hostsite
Revises: r2userlasttenant
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "r3hostsite"
down_revision: Union[str, None] = "r2userlasttenant"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMN = "site_id"
_INDEX = "ix_host_site_id"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=36), nullable=True))
    idx_names = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _INDEX not in idx_names:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    idx_names = {i["name"] for i in insp.get_indexes(_TABLE)}
    if _INDEX in idx_names:
        op.drop_index(_INDEX, table_name=_TABLE)
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
