# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""cloud backup is one-way: turn cloud_backup_account.auto_delete off (2026-11-04)

iCloud Photos backup only ever copies from iCloud to the storage host, and
nothing is ever deleted on either side (Bryan, 2026-11-04).  The per-account
"delete" setting is gone from the UI, the API and the agent, and no current
code reads or writes the column.  This revision switches it off for every
account, so a value left in it is false wherever it is read.

Expand-contract: this is the expand half.  The column itself stays until a
later release, once every database in the fleet is past this revision; its
server default (false) covers inserts by code that no longer names it.
Dropping it in the same release as the code change would break the
fan-out window, where a not-yet-migrated tenant is served by older code.

Idempotent; safe on SQLite + PostgreSQL.  Downgrade is a no-op: the values
switched off here are not put back.

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


def _has_column(bind):
    if _TABLE not in set(inspect(bind).get_table_names()):
        return False  # the bootstrap database: no tenant tables
    return _COLUMN in {column["name"] for column in inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind):
        account = sa.table(_TABLE, sa.column(_COLUMN, sa.Boolean()))
        bind.execute(
            account.update()
            .where(account.c.auto_delete == sa.true())
            .values(auto_delete=sa.false())
        )


def downgrade() -> None:
    pass  # nothing to undo: the switched-off values are not put back
