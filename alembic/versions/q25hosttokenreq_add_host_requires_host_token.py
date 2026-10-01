# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host.requires_host_token (Phase 22.0 agent identity)

Once a host's agent proves it keeps its token, the legacy id-only identity is
refused for that host (backend/security/agent_identity.py).  Every existing
host starts at false: today's agents keep working, and each host tightens as
its agent updates.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q25hosttokenreq
Revises: q24malwarejob
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q25hosttokenreq"
down_revision: Union[str, None] = "q24malwarejob"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMN = "requires_host_token"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TABLE)}:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TABLE)}:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
