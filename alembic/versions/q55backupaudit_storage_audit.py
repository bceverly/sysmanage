# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup storage audit: the service account and each repository's audit (2026-10-22)

Tenant data.  ``backup_target.service_account`` is the storage host's backup
account every export maps hosts to (NULL = ``restate``).
``backup_policy.storage_audit`` / ``storage_audit_at`` are the storage
host's latest read-only audit of that host's repository -- its NFS
baseline, its own filesystem and export, the export's client restriction
and mapping, and the append-only directory layout -- as JSON findings.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q55backupaudit
Revises: q54backupsnapname
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q55backupaudit"
down_revision: Union[str, None] = "q54backupsnapname"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMNS = {
    "backup_target": (sa.Column("service_account", sa.String(32), nullable=True),),
    "backup_policy": (
        sa.Column("storage_audit", sa.Text(), nullable=True),
        sa.Column("storage_audit_at", sa.DateTime(), nullable=True),
    ),
}


def _existing(table):
    insp = inspect(op.get_bind())
    if table not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    for table, columns in _COLUMNS.items():
        present = _existing(table)
        if present is None:
            continue
        for column in columns:
            if column.name not in present:
                op.add_column(table, column)


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        present = _existing(table)
        if present is None:
            continue
        drop = [c.name for c in columns if c.name in present]
        if drop:
            with op.batch_alter_table(table) as batch:
                for name in drop:
                    batch.drop_column(name)
