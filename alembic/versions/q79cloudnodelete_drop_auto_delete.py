# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""cloud backup is one-way: drop cloud_backup_account.auto_delete (2026-11-04)

iCloud Photos backup only ever copies from iCloud to the storage host, and
nothing is ever deleted on either side (Bryan, 2026-11-04).  The per-account
"delete" setting is gone from the UI, the API and the agent, so its column
goes too: a value left in it must not survive to be read by anything later.

Idempotent; safe on SQLite + PostgreSQL.  Downgrade puts the column back,
off for every account.

Revision ID: q79cloudnodelete
Revises: q78cloudbackup
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q79cloudnodelete"
down_revision: Union[str, None] = "q78cloudbackup"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "cloud_backup_account"
_COLUMN = "auto_delete"


def _columns(bind):
    if _TABLE not in set(inspect(bind).get_table_names()):
        return None  # the bootstrap database: no tenant tables
    return {column["name"] for column in inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is not None and _COLUMN in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is not None and _COLUMN not in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(
                sa.Column(
                    _COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()
                )
            )
