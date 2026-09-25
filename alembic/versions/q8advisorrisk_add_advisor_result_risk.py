# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add impact / likelihood / risk to advisor_result (Phase 21.2 S3)

``risk`` is impact x likelihood and is set ONLY when the rule fires: a host
with no finding has no finding risk, and a host that could not be assessed
must never read as risk 0. Stored per row so the S4 feed can order by it in
SQL rather than re-reading every rule.

Nullable, additive (expand-only); existing rows get NULL and are filled on
the next evaluation tick.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q8advisorrisk
Revises: q7advisor
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q8advisorrisk"
down_revision: Union[str, None] = "q7advisor"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "advisor_result"
_COLUMNS = ("impact", "likelihood", "risk")
_INDEX = "ix_advisor_result_risk"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    present = {c["name"] for c in insp.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name not in present:
            op.add_column(_TABLE, sa.Column(name, sa.Integer(), nullable=True))
    if _INDEX not in {i["name"] for i in insp.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["outcome", "risk"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return
    if _INDEX in {i["name"] for i in insp.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    present = {c["name"] for c in insp.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name in _COLUMNS:
            if name in present:
                batch.drop_column(name)
