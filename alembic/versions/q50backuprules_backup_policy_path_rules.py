# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: path rules + a pending "back up now" (ROADMAP 24.4, 2026-10-20)

Tenant data.  ``keep_paths`` and ``skip_paths`` are JSON lists of restate
path patterns: what to back up although the built-in rules leave it out
(e.g. ~/Downloads), and what to leave out (caches, Nextcloud previews).  The
host's agent writes them into the policy's own root-owned rules file.  NULL
means none.  ``capture_requested_at`` is a "Back up now" for many hosts that
waits for a free slot under the target's concurrency cap; NULL when none is
pending.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q50backuprules
Revises: q49backupfs
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q50backuprules"
down_revision: Union[str, None] = "q49backupfs"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"


def _new_columns():
    return (
        sa.Column("keep_paths", sa.Text(), nullable=True),
        sa.Column("skip_paths", sa.Text(), nullable=True),
        sa.Column("capture_requested_at", sa.DateTime(), nullable=True),
    )


def _existing():
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _existing()
    if columns is None:
        return
    for column in _new_columns():
        if column.name not in columns:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    columns = _existing()
    if columns is None:
        return
    drop = [c.name for c in _new_columns() if c.name in columns]
    if drop:
        with op.batch_alter_table(_TABLE) as batch:
            for name in drop:
                batch.drop_column(name)
