# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add advisor_proposal -- remediation the advisor PROPOSES (Phase 21.2 S5)

One row per proposed fix for one host's finding. Created and refreshed by the
evaluation tick, never applied without an operator's approval, which goes
through the existing config-profile apply path (and its maintenance-window
gate). A curated rule is referenced SOFTLY (``shared_rule_id``, no FK).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q9advisorfix
Revises: q8advisorrisk
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q9advisorfix"
down_revision: Union[str, None] = "q8advisorrisk"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "advisor_proposal"


def upgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        _TABLE,
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
            sa.ForeignKey("advisor_rule.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=True),
        sa.Column("engine", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("packages", sa.JSON(), nullable=True),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey("config_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("command_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_advisor_proposal_host_id", _TABLE, ["host_id"])
    op.create_index(
        "ix_advisor_proposal_host_rule", _TABLE, ["host_id", "rule_source", "rule_key"]
    )
    op.create_index("ix_advisor_proposal_status", _TABLE, ["status"])
    op.create_index("ix_advisor_proposal_command_id", _TABLE, ["command_id"])


def downgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(_TABLE)
