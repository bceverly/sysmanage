# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add federation_sync_queue.next_attempt_at (Phase 22.5)

When a sync entry fails, the moment it may be retried is computed once and
stored here, and the outbound worker selects ready rows in SQL.  Before, it
read the oldest rows and filtered their backoff in Python -- with fresh
jitter on every check, so a row's readiness flickered -- and newer ready rows
behind a window of waiting ones were never reached.

Existing rows keep NULL (ready at once, then scheduled on their next
failure).  Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q30fedsyncnext
Revises: q29regnonce
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q30fedsyncnext"
down_revision: Union[str, None] = "q29regnonce"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "federation_sync_queue"
_COLUMN = "next_attempt_at"
_INDEX = "ix_federation_sync_queue_next_attempt_at"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))
    if _INDEX not in {i["name"] for i in inspect(op.get_bind()).get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _INDEX in {i["name"] for i in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
