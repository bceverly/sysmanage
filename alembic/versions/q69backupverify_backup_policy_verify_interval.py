# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: scheduled verification cadence (Pro+ 24.6, 2026-10-28)

Tenant data.  verify_interval_days: run restate's check --read-all on
the backed-up host every N days -- a periodic test restore that writes
nothing (encrypted repositories with the policy's keys for that one job).
NULL or 0 = off.  Setting it needs the Pro+ backup engine.  Additive,
idempotent; safe on SQLite + PostgreSQL.

Revision ID: q69backupverify
Revises: q68backupyearly
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q69backupverify"
down_revision: Union[str, None] = "q68backupyearly"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = (("verify_interval_days", sa.Integer()),)


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
