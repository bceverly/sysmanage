# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host.registration_nonce_hash (Phase 22 idempotent registration)

An agent sends a random nonce with every registration attempt; the server
keeps its SHA-256 here when it creates the host.  A retry with the same nonce
gets the host's id and token again -- so a reply lost on the way (a timeout,
a server restart) no longer leaves the agent without its credential, refused
forever.  Cleared the first time the agent proves its token.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q29regnonce
Revises: q28mqdrainorder
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q29regnonce"
down_revision: Union[str, None] = "q28mqdrainorder"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMN = "registration_nonce_hash"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
