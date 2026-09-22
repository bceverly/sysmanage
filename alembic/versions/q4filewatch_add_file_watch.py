# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add watched-file state + watch lists to the tenant partition (Phase 21.1 S7)

S7 extends the 20.2 golden-host differ to arbitrary file and config state. The
tenant side of that is three things:

  * ``file_watch`` / ``file_watch_path`` — watch lists a customer wrote.
  * ``file_watch_assignment`` — which hosts watch which list. Mirrors
    ``query_pack_assignment``, including the SOFT ``shared_watch_id`` (no FK:
    it crosses the partition boundary).
  * ``host_file_state`` — one row per (host, watched path), whatever happened
    to it. ``absent`` and ``unreadable`` are STORED, not omitted: a table
    holding only the files that exist makes a deleted config file
    indistinguishable from one nobody watched, and the differ then silently
    misses the deletion.

No file CONTENT is stored anywhere here, deliberately — a sha256 answers "did
this change" without the bytes ever entering this database. That is what lets
an operator watch /etc/shadow.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q4filewatch
Revises: q3livequery
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q4filewatch"
down_revision: Union[str, None] = "q3livequery"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_WATCH = "file_watch"
_WATCH_PATH = "file_watch_path"
_ASSIGN = "file_watch_assignment"
_STATE = "host_file_state"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _WATCH not in names:
        op.create_table(
            _WATCH,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("name", name="uq_file_watch_name"),
        )

    if _WATCH_PATH not in names:
        op.create_table(
            _WATCH_PATH,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("watch_id", GUID(), nullable=False),
            sa.Column("path", sa.String(length=1024), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            # A list naming /etc/ssh/sshd_config must not make a Windows host
            # report it ABSENT — absent means "should be here and is not",
            # which is drift, and that one would be fabricated.
            sa.Column("platforms", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(
                ["watch_id"], ["file_watch.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("watch_id", "path", name="uq_file_watch_path"),
        )
        op.create_index("ix_file_watch_path_watch", _WATCH_PATH, ["watch_id"])

    if _ASSIGN not in names:
        op.create_table(
            _ASSIGN,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("watch_id", GUID(), nullable=True),
            # SOFT reference to shared_file_watch.id — no FK on purpose, the
            # shared catalog can be a separate database under scale-out.
            sa.Column("shared_watch_id", GUID(), nullable=True),
            sa.Column("host_id", GUID(), nullable=True),
            sa.Column("tag_id", GUID(), nullable=True),
            sa.Column("site_id", GUID(), nullable=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "interval_minutes", sa.Integer(), nullable=False, server_default="60"
            ),
            sa.Column("last_watch_version", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_dispatched_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["watch_id"], ["file_watch.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["site_id"], ["federation_sites.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_file_watch_assignment_enabled", _ASSIGN, ["enabled", "watch_id"]
        )
        op.create_index(
            "ix_file_watch_assignment_shared", _ASSIGN, ["enabled", "shared_watch_id"]
        )
        op.create_index(
            "ix_file_watch_assignment_shared_id", _ASSIGN, ["shared_watch_id"]
        )

    if _STATE not in names:
        op.create_table(
            _STATE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("path", sa.String(length=1024), nullable=False),
            # NOT NULL: a null state would reintroduce the exact ambiguity
            # this column exists to remove.
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=True),
            sa.Column("size", sa.Integer(), nullable=True),
            sa.Column("mode", sa.String(length=8), nullable=True),
            sa.Column("uid", sa.Integer(), nullable=True),
            sa.Column("gid", sa.Integer(), nullable=True),
            sa.Column("owner", sa.String(length=255), nullable=True),
            sa.Column("group_name", sa.String(length=255), nullable=True),
            sa.Column("mtime", sa.Integer(), nullable=True),
            sa.Column("type", sa.String(length=16), nullable=True),
            sa.Column("target", sa.String(length=1024), nullable=True),
            sa.Column("collected_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("host_id", "path", name="uq_host_file_state_path"),
        )
        op.create_index("ix_host_file_state_host_id", _STATE, ["host_id"])
        op.create_index("ix_host_file_state_host", _STATE, ["host_id", "path"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    # Children before parents.
    for table in (_STATE, _ASSIGN, _WATCH_PATH, _WATCH):
        if table in names:
            op.drop_table(table)
