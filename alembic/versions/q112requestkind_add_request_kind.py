# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Four-eyes approval for any kind of request (27.2, 2026-11-24).

``backup_restore_request.kind``: what is waiting for a second approver --
``restore`` (every request so far), and later ``rebuild``, ``clone``,
``wipe`` and ``migrate``.  ``target``: JSON naming where a rebuild or clone
goes (a hypervisor host, a discovered machine, another enrolled host); the
new host has no row yet, so ``host_id`` stays the source.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q112requestkind
Revises: q111ingestnotes
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q112requestkind"
down_revision: Union[str, None] = "q111ingestnotes"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_restore_request"


def _columns(inspector):
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    have = _columns(inspector)
    if "kind" not in have:
        op.add_column(
            _TABLE,
            sa.Column("kind", sa.String(16), nullable=False, server_default="restore"),
        )
    if "target" not in have:
        op.add_column(_TABLE, sa.Column("target", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    have = _columns(inspector)
    with op.batch_alter_table(_TABLE) as batch:
        for column in ("target", "kind"):
            if column in have:
                batch.drop_column(column)
