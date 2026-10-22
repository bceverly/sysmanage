# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: the NFSv4 path of a host's repository (2026-10-22)

Tenant data.  ``backup_policy.storage_nfs_path`` is the path a backed-up
host mounts over NFSv4 to reach its repository, as the storage host's agent
reported it (relative to the storage host's NFSv4 root).  The server sends
it to the host with the storage host's address, and the host's agent mounts
the export only while a backup job runs -- nobody edits fstab.

Additive (filled in by the next storage configure); also bumps every
policy's ``config_version`` so storage hosts report it now.  Idempotent in
effect; safe on SQLite + PostgreSQL.

Revision ID: q57backupnfspath
Revises: q56backupaddr
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q57backupnfspath"
down_revision: Union[str, None] = "q56backupaddr"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"
_COLUMN = "storage_nfs_path"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(1024), nullable=True))
    op.execute(sa.text(f"UPDATE {_TABLE} SET config_version = config_version + 1"))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    if _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
