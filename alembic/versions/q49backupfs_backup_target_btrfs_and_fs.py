# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_target: btrfs seal + the storage filesystem (ROADMAP 24.5, 2026-10-20)

Tenant data.  ``seal_mode`` gains "btrfs_snapshot" (no schema change: it is a
string); ``btrfs_snapshot_dir`` is where its read-only snapshots go (the
subvolume is the target's ``storage_path``).  ``storage_fs_type``,
``storage_fs_mount``, ``storage_fs_checked_at`` and
``storage_is_btrfs_subvolume`` record what the storage host's agent last
reported about the filesystem under ``storage_path``, so the server can warn
when it cannot take snapshots or when the seal mode cannot work there.  All
nullable: NULL means "not reported yet".

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q49backupfs
Revises: q48backups
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q49backupfs"
down_revision: Union[str, None] = "q48backups"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_target"


def _new_columns():
    return (
        sa.Column("btrfs_snapshot_dir", sa.String(1024), nullable=True),
        sa.Column("storage_fs_type", sa.String(64), nullable=True),
        sa.Column("storage_fs_mount", sa.String(1024), nullable=True),
        sa.Column("storage_fs_checked_at", sa.DateTime(), nullable=True),
        sa.Column("storage_is_btrfs_subvolume", sa.Boolean(), nullable=True),
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
