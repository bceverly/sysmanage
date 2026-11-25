# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Dispatch correlations in the database (2026-11-25).

``dispatch_correlation``: the engine a dispatched plan's result belongs to,
keyed by the queue message_id the agent echoes back.  It was process memory,
so with several server workers a result handled by another worker was
dropped.  Pure additive CREATE TABLE; idempotent and identical on SQLite and
PostgreSQL.

Revision ID: q115dispatchcorr
Revises: q114fleetrestore
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "q115dispatchcorr"
down_revision: Union[str, None] = "q114fleetrestore"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "dispatch_correlation"


def upgrade() -> None:
    if _TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("message_id", sa.String(80), primary_key=True),
        sa.Column("engine", sa.String(40), nullable=False),
        sa.Column("primary_id", sa.String(255), nullable=False),
        sa.Column("host_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
    )


def downgrade() -> None:
    if _TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(_TABLE)
