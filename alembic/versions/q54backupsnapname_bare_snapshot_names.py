# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup snapshot names: <repository>::<name> -> <name> (2026-10-21)

Tenant data, no schema change.  A capture's result names its snapshot as
``<repository>::<name>`` and the server stored that whole string, while
restore, prune, du and the snapshot listing all use the bare ``<name>``: the
Restore files dialog then sent a name the API refuses, and du's sizes never
matched.  Rows already stored are renamed to the bare name; where a bare-name
row for the same policy already exists (from a listing), the duplicate
qualified row is removed.  ``backup_run.snapshot`` is trimmed the same way.

Idempotent: a second run finds no ``::`` left.  Safe on SQLite + PostgreSQL.

Revision ID: q54backupsnapname
Revises: q53backuprundismiss
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q54backupsnapname"
down_revision: Union[str, None] = "q53backuprundismiss"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _bare(value: str) -> str:
    return value.rsplit("::", 1)[-1]


def _fix_snapshots(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, policy_id, name FROM backup_snapshot WHERE name LIKE '%::%'"
        )
    ).fetchall()
    for row_id, policy_id, name in rows:
        bare = _bare(name)
        clash = bind.execute(
            sa.text(
                "SELECT id FROM backup_snapshot WHERE policy_id = :p AND name = :n"
            ),
            {"p": policy_id, "n": bare},
        ).first()
        if clash is not None:
            bind.execute(
                sa.text("DELETE FROM backup_snapshot WHERE id = :i"), {"i": row_id}
            )
        else:
            bind.execute(
                sa.text("UPDATE backup_snapshot SET name = :n WHERE id = :i"),
                {"n": bare, "i": row_id},
            )


def _fix_runs(bind) -> None:
    rows = bind.execute(
        sa.text("SELECT id, snapshot FROM backup_run WHERE snapshot LIKE '%::%'")
    ).fetchall()
    for row_id, snapshot in rows:
        bind.execute(
            sa.text("UPDATE backup_run SET snapshot = :s WHERE id = :i"),
            {"s": _bare(snapshot), "i": row_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "backup_snapshot" in tables:
        _fix_snapshots(bind)
    if "backup_run" in tables:
        _fix_runs(bind)


def downgrade() -> None:
    # Nothing to undo: the bare name is the snapshot's real name.
    pass
