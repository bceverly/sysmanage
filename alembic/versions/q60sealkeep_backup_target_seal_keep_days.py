# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_target: seal retention and storage-space thresholds (2026-10-23)

Tenant data.  Every good backup is sealed with a ZFS or read-only btrfs
snapshot; until now nothing ever removed them, and the docs left their
retention to the administrator.  ``backup_target.seal_keep_days`` (NULL = the
default, 14) is sent with the seal job, and after each seal the storage host
removes its own seals older than that, never the newest.
``space_low_percent`` / ``space_critical_percent`` (NULL = 85 / 95) are when
the target card warns that the storage path is filling up.

Also bumps every policy's ``config_version`` so storage hosts get the new
seal job now.  Additive, idempotent in effect; safe on SQLite + PostgreSQL.

Revision ID: q60sealkeep
Revises: q59backupprotect
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q60sealkeep"
down_revision: Union[str, None] = "q59backupprotect"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


_COLUMNS = ("seal_keep_days", "space_low_percent", "space_critical_percent")


def upgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "backup_target" in tables:
        present = {c["name"] for c in insp.get_columns("backup_target")}
        for name in _COLUMNS:
            if name not in present:
                op.add_column(
                    "backup_target", sa.Column(name, sa.Integer(), nullable=True)
                )
    if "backup_policy" in tables:
        op.execute(
            sa.text("UPDATE backup_policy SET config_version = config_version + 1")
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_target" not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns("backup_target")}
    drop = [name for name in _COLUMNS if name in present]
    if drop:
        with op.batch_alter_table("backup_target") as batch:
            for name in drop:
                batch.drop_column(name)
