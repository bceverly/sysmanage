# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy token rotation (ROADMAP 25.5 exit criteria, 2026-11-13).

``backup_policy.proxy_token_sha256_next`` keeps the SHA-256 of the token a
host has made to replace its current one but does not use yet: the storage
host's grant takes it beside the current one, and the host switches to it
only once the storage host has acknowledged that grant, so no backup is ever
refused in between.  None: no rotation under way.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q87tokennext
Revises: q86proxybandwidth
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q87tokennext"
down_revision: Union[str, None] = "q86proxybandwidth"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = "backup_policy"
_COLUMN = "proxy_token_sha256_next"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _POLICY not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_POLICY)}:
        op.add_column(_POLICY, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _POLICY not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_POLICY)}:
        with op.batch_alter_table(_POLICY) as batch:
            batch.drop_column(_COLUMN)
