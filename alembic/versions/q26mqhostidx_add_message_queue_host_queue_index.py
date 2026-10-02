# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add ix_message_queue_host_queue (Phase 22.2 intake throughput)

The inbound drain takes each host's queue oldest first.  With no index on
host_id every per-host dequeue walked the whole backlog -- 9 ms each at 45k
pending rows, which spent the drain's whole time budget on scanning.  With
(host_id, direction, status, created_at): 0.05 ms.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q26mqhostidx
Revises: q25hosttokenreq
"""

from typing import Union

from sqlalchemy import inspect

from alembic import op

revision: str = "q26mqhostidx"
down_revision: Union[str, None] = "q25hosttokenreq"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "message_queue"
_INDEX = "ix_message_queue_host_queue"


def _indexes():
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    if _TABLE not in inspect(op.get_bind()).get_table_names():
        return
    if _INDEX not in _indexes():
        op.create_index(
            _INDEX, _TABLE, ["host_id", "direction", "status", "created_at"]
        )


def downgrade() -> None:
    if _TABLE not in inspect(op.get_bind()).get_table_names():
        return
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
