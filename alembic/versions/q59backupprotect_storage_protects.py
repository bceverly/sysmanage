# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: storage-side protect; the host's quiesce hooks (2026-10-22)

Tenant data.  restate 2.1.0.1 adds ``protect``: run on the storage host after
each capture, it makes every finished pack and snapshot root's and read-only
and the repository's directories sticky, so a host can add backups but change
or remove none.  The storage host's agent installs the job only where its
restate has the command; ``backup_policy.storage_protects`` records whether
it did (from the configure reply), so the server puts ``protect`` in the
chain -- capture, protect, seal, prune -- only where it can run.

``backup_policy.available_hooks`` (JSON list) is the quiesce hooks the
backed-up host's restate reports present (2.1+ lists only hooks whose
application is installed there), so the policy dialog offers a pick-list.

Also bumps every policy's ``config_version`` so storage hosts get the job
now.  Additive, idempotent in effect; safe on SQLite + PostgreSQL.

Revision ID: q59backupprotect
Revises: q58vmmopenbsd80
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q59backupprotect"
down_revision: Union[str, None] = "q58vmmopenbsd80"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_policy"


def _columns():
    return (
        sa.Column(
            "storage_protects", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("available_hooks", sa.Text(), nullable=True),
    )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns(_TABLE)}
    for column in _columns():
        if column.name not in present:
            op.add_column(_TABLE, column)
    op.execute(sa.text(f"UPDATE {_TABLE} SET config_version = config_version + 1"))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns(_TABLE)}
    drop = [c.name for c in _columns() if c.name in present]
    if drop:
        with op.batch_alter_table(_TABLE) as batch:
            for name in drop:
                batch.drop_column(name)
