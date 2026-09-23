# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add ad-hoc live queries to the tenant partition (Phase 21.1 S5)

A live query is one statement an operator types at a console and fans out
across a fleet. It is DISPATCHED as a one-query pack, so the agent command and
the result-correlation path are the ones S4 already proved; what this adds is
the part a pack does not carry -- the BOUNDS.

  * ``query_pack_live_query`` -- the request, with its concurrency, per-host
    timeout and counters.
  * ``query_pack_run.live_query_id`` -- a run belongs to an assignment
    (scheduled) or a live query (ad-hoc), never both. Reusing the run table
    means results, grading and the "not covered is not empty" property are
    shared rather than reimplemented.

Nullable and additive: existing scheduled runs are untouched and read as
``live_query_id IS NULL``.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q3livequery
Revises: q2qpacks
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q3livequery"
down_revision: Union[str, None] = "q2qpacks"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_LIVE = "query_pack_live_query"
_RUN = "query_pack_run"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _LIVE not in names:
        op.create_table(
            _LIVE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("sql", sa.Text(), nullable=False),
            sa.Column("required_tables", sa.JSON(), nullable=True),
            sa.Column(
                "status", sa.String(length=20), nullable=False, server_default="pending"
            ),
            # Bounds live WITH the request so what a run actually did stays
            # answerable after the fact, rather than depending on whatever the
            # server policy happened to be at the time.
            sa.Column("concurrency", sa.Integer(), nullable=False, server_default="20"),
            sa.Column(
                "timeout_seconds", sa.Integer(), nullable=False, server_default="120"
            ),
            sa.Column(
                "total_targets", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "completed_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            # Separate from failures: a host that does not serve the tables has
            # not failed, and merging them would make a Windows box look broken
            # for lacking ``mounts``.
            sa.Column(
                "not_covered_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("requested_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_query_pack_live_query_id", _LIVE, ["id"])
        op.create_index(
            "ix_query_pack_live_query_status", _LIVE, ["status", "created_at"]
        )

    if _RUN in names:
        columns = {c["name"] for c in insp.get_columns(_RUN)}
        if "live_query_id" not in columns:
            op.add_column(_RUN, sa.Column("live_query_id", GUID(), nullable=True))
            op.create_index("ix_query_pack_run_live_query", _RUN, ["live_query_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _RUN in names:
        columns = {c["name"] for c in insp.get_columns(_RUN)}
        if "live_query_id" in columns:
            op.drop_index("ix_query_pack_run_live_query", table_name=_RUN)
            op.drop_column(_RUN, "live_query_id")
    if _LIVE in names:
        op.drop_table(_LIVE)
