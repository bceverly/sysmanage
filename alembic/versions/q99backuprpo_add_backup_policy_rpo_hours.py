# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Restore readiness (27.1): a policy's recovery point objective, and a
federated site's readiness counts at the controller.

``backup_policy.rpo_hours`` -- the oldest the last good backup may be before
the host's restore readiness says "RPO breached"; NULL keeps the default,
twice the policy's interval.  Read by the Enterprise backup_ops_engine.
``federation_backup_rollup.readiness_counts_json`` -- a site's hosts by
readiness state, in its backup status snapshot.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q99backuprpo
Revises: q98rebootunsafe
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q99backuprpo"
down_revision: Union[str, None] = "q98rebootunsafe"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMNS = (
    ("backup_policy", "rpo_hours", sa.Integer),
    ("federation_backup_rollup", "readiness_counts_json", sa.Text),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column, kind in _COLUMNS:
        if table not in tables:
            continue
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, kind(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column, _kind in _COLUMNS:
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
