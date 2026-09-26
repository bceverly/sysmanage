# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add shared_advisor_rule_pack.default_enabled (Phase 21.2 S6)

Whether a tenant that has not chosen gets a curated pack. Additive
(expand-only); existing packs default to off, and the catalog sync sets the
value the engine ships.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s15advisordefault
Revises: s14advisor
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "s15advisordefault"
down_revision: Union[str, None] = "s14advisor"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "shared_advisor_rule_pack"
_COLUMN = "default_enabled"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in insp.get_columns(_TABLE)}:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names() and _COLUMN in {
        c["name"] for c in insp.get_columns(_TABLE)
    }:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
