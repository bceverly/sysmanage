# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: grandfather-father-son retention (Pro+ 24.6, 2026-10-27)

Tenant data.  Beside ``keep_last``, a policy may keep the newest snapshot of
each of the last N days, ISO weeks and months that have one -- restate's
``prune --keep-daily/--keep-weekly/--keep-monthly`` (the storage host's
prune job).  NULL or 0 = not used.  Setting them needs the Pro+ backup
engine; once set they are always honored, so a lapsed license can never make
a prune delete history the operator chose to keep.  Additive, idempotent;
safe on SQLite + PostgreSQL.

Revision ID: q67backupgfs
Revises: q66backupkeyrotate
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q67backupgfs"
down_revision: Union[str, None] = "q66backupkeyrotate"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = (
    ("keep_daily", sa.Integer()),
    ("keep_weekly", sa.Integer()),
    ("keep_monthly", sa.Integer()),
)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    for name, kind in _POLICY:
        if name not in present:
            op.add_column("backup_policy", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    drop = [name for name, _kind in _POLICY if name in present]
    if drop:
        with op.batch_alter_table("backup_policy") as batch:
            for name in drop:
                batch.drop_column(name)
