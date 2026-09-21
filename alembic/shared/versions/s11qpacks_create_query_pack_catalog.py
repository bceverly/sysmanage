# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create the curated query-pack catalog in the shared partition (Phase 21.1 S4)

A curated pack -- "listening ports on non-standard interfaces" -- is the same
query for every customer, so the catalog lives ONCE here, like the CVE,
advisory and OS-lifecycle registries.  Per-tenant ASSIGNMENT of those packs is
the tenant chain's business (``q2qpacks``), and the reference from there is
SOFT: no cross-partition ForeignKey.

  * ``shared_query_pack`` -- the pack, versioned and offline-updatable.
  * ``shared_query_pack_query`` -- its queries (intra-shared FK, so real).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s11qpacks
Revises: s10clmviews
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "s11qpacks"
down_revision: Union[str, None] = "s10clmviews"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_PACK = "shared_query_pack"
_QUERY = "shared_query_pack_query"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _PACK not in names:
        op.create_table(
            _PACK,
            sa.Column("id", GUID(), primary_key=True),
            # Stable identity across catalog refreshes: a re-ingest mints a new
            # uuid, so the slug is what an assignment survives on.
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column(
                "deprecated", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_shared_query_pack_slug"),
        )
        op.create_index("ix_shared_query_pack_slug", _PACK, ["slug"])
        op.create_index("ix_shared_query_pack_category", _PACK, ["category"])
        op.create_index("ix_shared_query_pack_enabled", _PACK, ["deprecated"])

    if _QUERY not in names:
        op.create_table(
            _QUERY,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "shared_pack_id",
                GUID(),
                sa.ForeignKey(f"{_PACK}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("sql", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            # DECLARED, not parsed from the SQL: the agent compares this
            # against its own fact coverage to decide whether the query can be
            # answered honestly, and inferring it would be wrong in exactly the
            # cases that matter (joins, subqueries, CTEs).
            sa.Column("required_tables", sa.JSON(), nullable=True),
            sa.Column(
                "interval_minutes", sa.Integer(), nullable=False, server_default="60"
            ),
            sa.Column("platforms", sa.JSON(), nullable=True),
            sa.UniqueConstraint(
                "shared_pack_id", "name", name="uq_shared_query_pack_query_name"
            ),
        )
        op.create_index("ix_shared_query_pack_query_pack", _QUERY, ["shared_pack_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    for table in (_QUERY, _PACK):
        if table in names:
            op.drop_table(table)
