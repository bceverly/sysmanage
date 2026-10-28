# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: yearly retention + the storage host's restate abilities (2026-10-28)

Tenant data.  keep_yearly: the newest snapshot of each of the last N
years that have one -- restate's prune --keep-yearly (2.2.0.12).  NULL or
0 = not used; set with the other grandfather-father-son counts (Pro+), always
honored once set.  storage_abilities: what the storage host's restate
reported at configure time (JSON list, e.g. ["keep_yearly"]), so a
yearly count is only accepted where the prune that honors it can run.
Additive, idempotent; safe on SQLite + PostgreSQL.

Revision ID: q68backupyearly
Revises: q67backupgfs
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q68backupyearly"
down_revision: Union[str, None] = "q67backupgfs"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = (
    ("keep_yearly", sa.Integer()),
    ("storage_abilities", sa.Text()),
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
