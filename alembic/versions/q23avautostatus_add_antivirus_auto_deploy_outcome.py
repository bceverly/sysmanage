# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""antivirus_auto_deploy: record what the agent answered (Phase 21.3)

Adds ``status``, ``command_id``, ``last_error`` and ``finished_at`` so an
automatic deploy is done only when the agent reports the plan succeeded, and
a failed plan is retried instead of being counted as delivered.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q23avautostatus
Revises: q22avwinclamav
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q23avautostatus"
down_revision: Union[str, None] = "q22avwinclamav"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "antivirus_auto_deploy"
_INDEX = "ix_antivirus_auto_deploy_command_id"
_COLUMNS = (
    ("status", sa.String(length=16)),
    ("command_id", sa.String(length=36)),
    ("last_error", sa.Text()),
    ("finished_at", sa.DateTime()),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, column_type in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, column_type, nullable=True))
    if _INDEX not in {i["name"] for i in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["command_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _INDEX in {i["name"] for i in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name, _type in reversed(_COLUMNS):
            if name in existing:
                batch.drop_column(name)
