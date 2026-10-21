# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_run.dismissed_at: "Clear" for the Backups page job list (2026-10-21)

Tenant data.  Clearing the job list hides finished runs from it rather than
deleting them: the scheduler and the status column read run history (the
last good capture, the last seal / prune / check), and the audit log keeps
every change anyway.  Old runs are deleted by the scheduler's retention
pass, which always keeps each kind's newest.  NULL = still listed.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q53backuprundismiss
Revises: q52pkgrevision
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q53backuprundismiss"
down_revision: Union[str, None] = "q52pkgrevision"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_run"
_COLUMN = "dismissed_at"


def _columns():
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns is not None and _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if columns is not None and _COLUMN in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
