# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's fullest local filesystem (2026-11-20).

``host.disk_used_percent`` / ``disk_fullest_mount`` / ``disk_available_bytes``
/ ``disk_checked_at`` -- from the host's disk list or its host metrics,
whichever came last, kept whatever the license, so a nearly full disk is
warned on before an update runs out of room part-way.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q104diskspace
Revises: q103fedbackuptargets
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q104diskspace"
down_revision: Union[str, None] = "q103fedbackuptargets"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMNS = (
    ("disk_used_percent", sa.Float),
    ("disk_fullest_mount", lambda: sa.String(255)),
    ("disk_available_bytes", sa.BigInteger),
    ("disk_checked_at", sa.DateTime),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "host" not in set(inspector.get_table_names()):
        return
    have = {c["name"] for c in inspector.get_columns("host")}
    for column, kind in _COLUMNS:
        if column not in have:
            op.add_column("host", sa.Column(column, kind(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "host" not in set(inspector.get_table_names()):
        return
    have = {c["name"] for c in inspector.get_columns("host")}
    with op.batch_alter_table("host") as batch:
        for column, _kind in _COLUMNS:
            if column in have:
                batch.drop_column(column)
