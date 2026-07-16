# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""mirror_repository: consecutive_sync_failures (tick backoff / auto-disable).

Revision ID: z7mirrorfail
Revises: z6ingest
Create Date: 2026-05-31 10:00:00.000000

``tick_mirrors`` re-dispatches every enabled mirror whose ``next_sync_at``
is due.  A mirror that fails every run (e.g. one too large to sync
without OOMing its host) would otherwise be re-dispatched on every cron
tick forever.  This column lets the result handler count consecutive
failures so the tick can apply an escalating skip and ultimately
auto-disable the mirror — with the count reset to 0 on any success.

Idempotent: the column add is guarded by an ``inspect()`` check.
SQLite- and PostgreSQL-safe.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "z7mirrorfail"
down_revision: Union[str, None] = "z6ingest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "mirror_repository"
_COLUMN = "consecutive_sync_failures"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    if _COLUMN in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        batch.add_column(
            sa.Column(
                _COLUMN,
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    if _COLUMN not in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        batch.drop_column(_COLUMN)
