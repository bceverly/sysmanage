# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add ix_message_queue_drain_order (Phase 22.2 intake throughput)

Each inbound drain round picks the hosts whose oldest due message is oldest.
It was a GROUP BY over every pending row: 61 ms a round with ~100k waiting at
10,000 agents (2026-10-02), 27% of the database's time.  It now reads due
rows oldest first until it has enough hosts, along this index.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q28mqdrainorder
Revises: q27invhostidx
"""

from typing import Union

from sqlalchemy import inspect

from alembic import op

revision: str = "q28mqdrainorder"
down_revision: Union[str, None] = "q27invhostidx"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "message_queue"
_INDEX = "ix_message_queue_drain_order"


def _indexes():
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    if _TABLE not in inspect(op.get_bind()).get_table_names():
        return
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, ["direction", "status", "created_at"])


def downgrade() -> None:
    if _TABLE not in inspect(op.get_bind()).get_table_names():
        return
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
