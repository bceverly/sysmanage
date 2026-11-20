# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Per-site backup targets through federation (27.3).

``federation_backup_rollup.targets_json`` -- a site's backup targets in its
status snapshot at the controller (names, use and health; never paths).
``backup_tag_policy.managed_by`` -- "federation" for a tag policy the
controller pushed to this site (edited only there); NULL = this site's own.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q103fedbackuptargets
Revises: q102multitarget
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q103fedbackuptargets"
down_revision: Union[str, None] = "q102multitarget"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMNS = (
    ("federation_backup_rollup", "targets_json", sa.Text),
    ("backup_tag_policy", "managed_by", lambda: sa.String(32)),
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
