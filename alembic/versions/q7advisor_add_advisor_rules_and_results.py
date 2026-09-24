# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add the advisor's tenant tables: customer rules and per-host outcomes (Phase 21.2 S2)

  * ``advisor_rule`` -- rules a customer wrote (curated rules live in the
    shared chain, ``s14advisor``).
  * ``advisor_result`` -- one row per (host, rule): fires / does_not_fire /
    not_assessable / not_applicable, with EVERY gap when it could not be
    evaluated.  A curated rule is referenced by ``shared_rule_id`` with NO
    ForeignKey -- it crosses a partition boundary.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q7advisor
Revises: q5updatesat
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q7advisor"
down_revision: Union[str, None] = "q5updatesat"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RULE = "advisor_rule"
_RESULT = "advisor_result"


def _create_rule_table() -> None:
    op.create_table(
        _RULE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lens", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="host"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("rule_key", name="uq_advisor_rule_key"),
    )
    op.create_index("ix_advisor_rule_id", _RULE, ["id"])


def _create_result_table() -> None:
    op.create_table(
        _RESULT,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_source", sa.String(length=16), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=False),
        # NO ForeignKey: a cross-partition soft reference by design.
        sa.Column("shared_rule_id", GUID(), nullable=True),
        sa.Column(
            "rule_id",
            GUID(),
            sa.ForeignKey(f"{_RULE}.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("lens", sa.String(length=32), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=True),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches", sa.JSON(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "host_id", "rule_source", "rule_key", name="uq_advisor_result_host_rule"
        ),
    )
    op.create_index("ix_advisor_result_host_id", _RESULT, ["host_id"])
    op.create_index("ix_advisor_result_shared_rule_id", _RESULT, ["shared_rule_id"])
    op.create_index("ix_advisor_result_rule_id", _RESULT, ["rule_id"])
    op.create_index(
        "ix_advisor_result_rule_outcome",
        _RESULT,
        ["rule_source", "rule_key", "outcome"],
    )
    op.create_index("ix_advisor_result_outcome", _RESULT, ["outcome"])


def upgrade() -> None:
    names = set(inspect(op.get_bind()).get_table_names())
    if _RULE not in names:
        _create_rule_table()
    if _RESULT not in names:
        _create_result_table()


def downgrade() -> None:
    names = set(inspect(op.get_bind()).get_table_names())
    for table in (_RESULT, _RULE):
        if table in names:
            op.drop_table(table)
