# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Swap for the antivirus memory floor: ``host.swap_total_mb`` and
``antivirus_auto_deploy.swap_added_mb``.

ClamAV is deployed only where memory clears a floor; swap now counts toward
it, and SysManage can add a swap file to close the gap (the swap it added is
kept so removing antivirus can offer to remove it).  Additive only;
idempotent and identical on SQLite and PostgreSQL.

Revision ID: q108avswap
Revises: q107move
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q108avswap"
down_revision: Union[str, None] = "q107move"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("host", "swap_total_mb", sa.BigInteger()),
    ("antivirus_auto_deploy", "swap_added_mb", sa.Integer()),
)


def _existing(table):
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return None
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    for table, name, kind in _COLUMNS:
        columns = _existing(table)
        if columns is not None and name not in columns:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for table, name, _kind in _COLUMNS:
        columns = _existing(table)
        if columns is not None and name in columns:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(name)
