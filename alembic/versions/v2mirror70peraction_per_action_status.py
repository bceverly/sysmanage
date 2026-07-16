# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Per-action status columns on mirror_repository + size_bytes/file_count fill-in.

Revision ID: v2mirror70peraction
Revises: u1mirror60ubresolute
Create Date: 2026-05-27 19:00:00.000000

The original schema collapsed every plan outcome — sync, snapshot,
restore, integrity_check, gc — onto one ``last_sync_*`` trio.  That
meant a successful sync followed by a failed snapshot stamped the
mirror row as ``FAILED`` and erased the operator's view of whether
the sync had ever worked.  This migration splits the column out:

    last_sync_*        (kept; now only the ``sync`` action writes it)
    last_snapshot_*    (new)
    last_restore_*     (new)
    last_integrity_*   (new)
    last_gc_*          (new)

Each group is ``_at``, ``_status``, ``_error``, ``_message_id``.  The
``_message_id`` is stamped at dispatch and cleared on result; the UI
keys off non-NULL ``_message_id`` to show an "in-flight" spinner and
elapsed-time chip.

``mirror_snapshot`` already has ``size_bytes`` + ``file_count``
columns; they're populated from rsync ``--stats`` output now that
the engine emits ``--stats`` (Phase 12 follow-up).  No column added
here.

Idempotent: each ``add_column`` is guarded by an ``inspect()`` check
so re-running on a partially-migrated DB is a no-op.  SQLite-safe via
``batch_alter_table``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "v2mirror70peraction"
down_revision: Union[str, None] = "u1mirror60ubresolute"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "mirror_repository"

# Per-action column groups.  Each tuple: (action_prefix, has_message_id).
# integrity_check and gc don't dispatch from UI buttons today so they
# don't need ``_message_id`` yet — but adding the column now avoids a
# second migration later when they grow buttons.
_ACTIONS = ("snapshot", "restore", "integrity", "gc")


def _existing_columns(bind, table: str) -> set:
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind, _TABLE)

    new_columns = []
    for action in _ACTIONS:
        new_columns.extend(
            [
                (f"last_{action}_at", sa.DateTime(), True),
                (f"last_{action}_status", sa.String(length=40), True),
                (f"last_{action}_error", sa.Text(), True),
                (f"last_{action}_message_id", sa.String(length=80), True),
            ]
        )
    # sync already exists in the original schema except for
    # ``last_sync_message_id`` — backfill that one so we get the
    # in-flight spinner on sync too.
    new_columns.append(("last_sync_message_id", sa.String(length=80), True))

    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        for name, coltype, nullable in new_columns:
            if name not in existing:
                batch.add_column(sa.Column(name, coltype, nullable=nullable))


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind, _TABLE)

    drop_columns = []
    for action in _ACTIONS:
        drop_columns.extend(
            [
                f"last_{action}_at",
                f"last_{action}_status",
                f"last_{action}_error",
                f"last_{action}_message_id",
            ]
        )
    drop_columns.append("last_sync_message_id")

    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        for name in drop_columns:
            if name in existing:
                batch.drop_column(name)
