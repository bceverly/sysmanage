# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""An escrow-keyed backup key has no OpenBAO reference (ROADMAP 25.9).

The SysManage server's own backup is encrypted to the operator's break-glass
escrow PUBLIC key; the secret half never touches the server, so its
``backup_policy_key`` row has a fingerprint and no ``key_ref``.  The column
was NOT NULL, and saving an escrow key failed with a NotNullViolation (server-
loss drill, 2026-11-09).  Every reader already skips a row without one
(backup_keys_read, backup_escrow, backup_breakglass).

Idempotent; safe on SQLite + PostgreSQL.  The downgrade restores NOT NULL only
when no row lacks a reference, and otherwise leaves the column as it is.

Revision ID: q83escrowkeyref
Revises: q82serverbackup
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q83escrowkeyref"
down_revision: Union[str, None] = "q82serverbackup"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy_key"
_COLUMN = "key_ref"


def _column():
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return None  # the bootstrap database: no tenant tables
    return next(
        (c for c in inspector.get_columns(_TABLE) if c["name"] == _COLUMN), None
    )


def upgrade() -> None:
    column = _column()
    if column is None or column["nullable"]:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(_COLUMN, existing_type=sa.String(length=1024), nullable=True)


def downgrade() -> None:
    column = _column()
    if column is None or not column["nullable"]:
        return
    # Fixed module constants, no input: not an injection.
    query = f"SELECT COUNT(*) FROM {_TABLE} WHERE {_COLUMN} IS NULL"  # nosec B608
    unreferenced = op.get_bind().execute(sa.text(query)).scalar()
    if unreferenced:
        return  # escrow-keyed rows would break the constraint: leave it nullable
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            _COLUMN, existing_type=sa.String(length=1024), nullable=False
        )
