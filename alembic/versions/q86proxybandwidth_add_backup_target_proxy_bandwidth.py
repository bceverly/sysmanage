# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy bandwidth by the hour (ROADMAP 25.5 limits, 25.7: Pro+).

``backup_target.proxy_bandwidth`` keeps the target's bandwidth rules as
restate-proxy's grant lines (JSON list: ``"08-18 2MiB/s"``, ``"20MiB/s"``);
every grant of the target carries them while the Pro+ backup engine is
loaded and the storage host can apply them.  None: no limit.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q86proxybandwidth
Revises: q85proxycert
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q86proxybandwidth"
down_revision: Union[str, None] = "q85proxycert"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TARGET = "backup_target"
_COLUMN = "proxy_bandwidth"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TARGET not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TARGET)}:
        op.add_column(_TARGET, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TARGET not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TARGET)}:
        with op.batch_alter_table(_TARGET) as batch:
            batch.drop_column(_COLUMN)
