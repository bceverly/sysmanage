# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add advisor_pack_setting -- a tenant's choice about a curated pack (Phase 21.2 S6)

No row means "the pack's default". Keyed by the pack's slug, a soft
reference into the shared catalog (no cross-partition FK).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q10advisorpack
Revises: q9advisorfix
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q10advisorpack"
down_revision: Union[str, None] = "q9advisorfix"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "advisor_pack_setting"


def upgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("pack_slug", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("disabled_rules", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("pack_slug", name="uq_advisor_pack_setting_slug"),
    )


def downgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(_TABLE)
