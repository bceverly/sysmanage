# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The SysManage server backs itself up (ROADMAP 25.9).

The server is a managed host like any other; its backup policy is that host's
own ``backup_policy`` row, marked by ``server_preset``.  A marked policy always
pauses the databases for the capture and always leaves OpenBAO's init
material and the server's OpenBAO token out of the backup, whatever its path
rules say: those go to the operator's escrow instead, so a stolen backup
cannot unseal the OpenBAO snapshot inside it.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q82serverbackup
Revises: q81reachnat
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q82serverbackup"
down_revision: Union[str, None] = "q81reachnat"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"
_COLUMN = "server_preset"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
