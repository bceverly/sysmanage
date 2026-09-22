# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create the curated file-watch catalog in the shared partition (Phase 21.1 S7)

A curated watch list -- "CIS Linux baseline config" -- is identical for every
customer, so it is global reference data and lives ONCE here, exactly like
``shared_query_pack`` and ``shared_advisory``. What is per-customer is which
hosts watch it, and that lives in the tenant chain (``q4filewatch``).

  * ``shared_file_watch`` -- the list, versioned and offline-updatable.
  * ``shared_file_watch_path`` -- its paths (intra-shared FK, so real).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s12filewatch
Revises: s11qpacks
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "s12filewatch"
down_revision: Union[str, None] = "s11qpacks"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_WATCH = "shared_file_watch"
_PATH = "shared_file_watch_path"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _WATCH not in names:
        op.create_table(
            _WATCH,
            sa.Column("id", GUID(), primary_key=True),
            # Stable identity across catalog refreshes: an assignment survives
            # on the slug, not on a locally minted uuid.
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("category", sa.String(length=64), nullable=True),
            # Retired rather than deleted: an assignment may still name it,
            # and "this list was withdrawn" beats a dangling reference.
            sa.Column(
                "deprecated", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_shared_file_watch_slug"),
        )
        op.create_index("ix_shared_file_watch_id", _WATCH, ["id"])
        op.create_index("ix_shared_file_watch_slug", _WATCH, ["slug"])
        op.create_index("ix_shared_file_watch_category", _WATCH, ["category"])
        op.create_index("ix_shared_file_watch_enabled", _WATCH, ["deprecated"])

    if _PATH not in names:
        op.create_table(
            _PATH,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("shared_watch_id", GUID(), nullable=False),
            sa.Column("path", sa.String(length=1024), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("platforms", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(
                ["shared_watch_id"], ["shared_file_watch.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "shared_watch_id", "path", name="uq_shared_file_watch_path"
            ),
        )
        op.create_index("ix_shared_file_watch_path_watch", _PATH, ["shared_watch_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    for table in (_PATH, _WATCH):
        if table in names:
            op.drop_table(table)
