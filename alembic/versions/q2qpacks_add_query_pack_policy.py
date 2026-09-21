# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add query-pack policy + results to the tenant partition (Phase 21.1 S4)

The curated CATALOG is shared partition (``s11qpacks``).  What belongs to a
customer is here:

  * ``query_pack`` / ``query_pack_query`` -- packs the customer wrote.
  * ``query_pack_assignment`` -- which hosts/tags/sites run which pack.
    Carries EITHER ``pack_id`` (real FK, same partition) OR
    ``shared_pack_id`` -- a SOFT reference with no ForeignKey, because the
    shared catalog is a different database under scale-out and the constraint
    could not be enforced there.  Same rule as ``host_vulnerability_finding``
    and ``host_applicable_advisory``.
  * ``query_pack_run`` / ``query_pack_result_row`` -- what came back.

Results are stored as ROWS rather than one blob per run: every S6 consumer
asks "which hosts returned a row matching X", which is a query over rows and
not a scan of documents.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q2qpacks
Revises: c23cfgfleet01
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q2qpacks"
down_revision: Union[str, None] = "c23cfgfleet01"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_PACK = "query_pack"
_QUERY = "query_pack_query"
_ASSIGNMENT = "query_pack_assignment"
_RUN = "query_pack_run"
_RESULT = "query_pack_result_row"


def _has_table(names, table):
    return table in names


def upgrade() -> None:  # pylint: disable=too-many-statements
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if not _has_table(names, _PACK):
        op.create_table(
            _PACK,
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
            sa.UniqueConstraint("name", name="uq_query_pack_name"),
        )
        op.create_index("ix_query_pack_id", _PACK, ["id"])

    if not _has_table(names, _QUERY):
        op.create_table(
            _QUERY,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "pack_id",
                GUID(),
                sa.ForeignKey(f"{_PACK}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("sql", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("required_tables", sa.JSON(), nullable=True),
            sa.Column(
                "interval_minutes", sa.Integer(), nullable=False, server_default="60"
            ),
            sa.Column("platforms", sa.JSON(), nullable=True),
            sa.UniqueConstraint("pack_id", "name", name="uq_query_pack_query_name"),
        )
        op.create_index("ix_query_pack_query_pack", _QUERY, ["pack_id"])

    if not _has_table(names, _ASSIGNMENT):
        op.create_table(
            _ASSIGNMENT,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "pack_id",
                GUID(),
                sa.ForeignKey(f"{_PACK}.id", ondelete="CASCADE"),
                nullable=True,
            ),
            # NO ForeignKey: cross-partition soft reference by design.
            sa.Column("shared_pack_id", GUID(), nullable=True),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "tag_id",
                GUID(),
                sa.ForeignKey("tags.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "site_id",
                GUID(),
                sa.ForeignKey("federation_sites.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "interval_minutes", sa.Integer(), nullable=False, server_default="60"
            ),
            sa.Column("last_pack_version", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_dispatched_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_query_pack_assignment_shared_id", _ASSIGNMENT, ["shared_pack_id"]
        )
        # The tick reads "enabled assignments, by pack"; without these it
        # scans every assignment on every pass.
        op.create_index(
            "ix_query_pack_assignment_enabled", _ASSIGNMENT, ["enabled", "pack_id"]
        )
        op.create_index(
            "ix_query_pack_assignment_shared",
            _ASSIGNMENT,
            ["enabled", "shared_pack_id"],
        )

    if not _has_table(names, _RUN):
        op.create_table(
            _RUN,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("assignment_id", GUID(), nullable=True),
            sa.Column("pack_id", GUID(), nullable=True),
            sa.Column("shared_pack_id", GUID(), nullable=True),
            sa.Column("pack_name", sa.String(length=255), nullable=True),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="pending"
            ),
            # The contract version the AGENT ran against: a fleet upgrades
            # gradually, and without this, comparing results across hosts
            # silently compares different contracts.
            sa.Column("contract_version", sa.Integer(), nullable=True),
            sa.Column(
                "queries_total", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("queries_ok", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "queries_not_covered", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "queries_failed", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_query_pack_run_id", _RUN, ["id"])
        op.create_index("ix_query_pack_run_host", _RUN, ["host_id"])
        op.create_index("ix_query_pack_run_assignment", _RUN, ["assignment_id"])
        op.create_index("ix_query_pack_run_pack", _RUN, ["pack_id"])
        op.create_index("ix_query_pack_run_shared_pack", _RUN, ["shared_pack_id"])
        op.create_index(
            "ix_query_pack_run_host_started", _RUN, ["host_id", "started_at"]
        )

    if not _has_table(names, _RESULT):
        op.create_table(
            _RESULT,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "run_id",
                GUID(),
                sa.ForeignKey(f"{_RUN}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("query_name", sa.String(length=128), nullable=False),
            # ``not_covered`` gets ONE row with a null payload: a record that
            # the question was asked and could not be answered here, which is
            # different from asking and getting nothing, and different again
            # from never asking.
            sa.Column(
                "status", sa.String(length=32), nullable=False, server_default="ok"
            ),
            sa.Column("reason", sa.String(length=64), nullable=True),
            sa.Column("columns", sa.JSON(), nullable=True),
            sa.Column("collected_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_query_pack_result_run", _RESULT, ["run_id"])
        op.create_index("ix_query_pack_result_query", _RESULT, ["run_id", "query_name"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    for table in (_RESULT, _RUN, _ASSIGNMENT, _QUERY, _PACK):
        if table in names:
            op.drop_table(table)
