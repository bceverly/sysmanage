# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create shared_threat_questionnaire -- the curated threat-model questionnaire (Phase 21.4 S2)

One row per questionnaire VERSION, synced from advisor_engine. Every version
is kept: a saved threat model names the version it was answered against.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s17threatq
Revises: s16osfeeds
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "s17threatq"
down_revision: Union[str, None] = "s16osfeeds"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "shared_threat_questionnaire"


def upgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "slug", "version", name="uq_shared_threat_questionnaire_version"
        ),
    )
    op.create_index(
        "ix_shared_threat_questionnaire_slug", _TABLE, ["slug"], unique=False
    )


def downgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(_TABLE)
