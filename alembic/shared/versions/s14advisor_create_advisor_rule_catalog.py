# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create the curated advisor rule catalog in the shared partition (Phase 21.2 S2)

A curated rule -- "critical CVE with a fix available" -- is the same rule for
every customer, so the catalog lives ONCE here, like the query-pack, CVE and
advisory catalogs.  Tenant-authored rules and every per-host outcome are the
tenant chain's business (``q7advisor``), and results reference a curated rule
SOFTLY: no cross-partition ForeignKey.

  * ``shared_advisor_rule_pack`` -- a pack, versioned and offline-updatable.
  * ``shared_advisor_rule`` -- its rules (intra-shared FK, so real).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s14advisor
Revises: s13cverelease
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "s14advisor"
down_revision: Union[str, None] = "s13cverelease"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_PACK = "shared_advisor_rule_pack"
_RULE = "shared_advisor_rule"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _PACK not in names:
        op.create_table(
            _PACK,
            sa.Column("id", GUID(), primary_key=True),
            # Stable identity across catalog refreshes: a re-ingest mints a new
            # uuid, so the slug is what a pack is known by offline.
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "deprecated", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_shared_advisor_rule_pack_slug"),
        )
        op.create_index("ix_shared_advisor_rule_pack_id", _PACK, ["id"])
        op.create_index("ix_shared_advisor_rule_pack_slug", _PACK, ["slug"])

    if _RULE not in names:
        op.create_table(
            _RULE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "shared_pack_id",
                GUID(),
                sa.ForeignKey(f"{_PACK}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            # The rule's own id ("SEC-001"), stable across its versions.
            sa.Column("rule_key", sa.String(length=64), nullable=False),
            sa.Column(
                "contract_version", sa.Integer(), nullable=False, server_default="1"
            ),
            sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("lens", sa.String(length=32), nullable=False),
            sa.Column(
                "scope", sa.String(length=16), nullable=False, server_default="host"
            ),
            sa.Column("title", sa.String(length=255), nullable=False),
            # The whole rule as the engine's contract describes it; the columns
            # above are copies kept for querying.
            sa.Column("definition", sa.JSON(), nullable=False),
            sa.UniqueConstraint(
                "shared_pack_id", "rule_key", name="uq_shared_advisor_rule_key"
            ),
        )
        op.create_index(
            "ix_shared_advisor_rule_shared_pack_id", _RULE, ["shared_pack_id"]
        )
        op.create_index("ix_shared_advisor_rule_rule_key", _RULE, ["rule_key"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    for table in (_RULE, _PACK):
        if table in names:
            op.drop_table(table)
