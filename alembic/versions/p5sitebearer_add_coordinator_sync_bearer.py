# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_coordinator_sync_bearer

Phase 12.10 Slice 2: federation wire protocol — site-side bearer
storage for the outbound sync worker.

Adds one nullable column to ``federation_coordinator``:

  ``sync_bearer_token``  — plaintext bearer the site presents on
                           every outbound sync POST.  Stored in
                           plaintext (unlike the coordinator-side
                           ``federation_sites.sync_bearer_token_hash``
                           which only keeps the SHA-256) because the
                           site must send the literal value on every
                           HTTP call.  Filesystem permissions on the
                           DB (postgres pg_hba + ``/etc/sysmanage.yaml``
                           secret-mode) protect it at rest; rotation
                           via the engine's enrollment refresh flow
                           replaces this value.

Idempotent + cross-dialect: guards on the column-exists check
before adding.

Revision ID: p5sitebearer
Revises: o4syncauth
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "p5sitebearer"
down_revision: Union[str, None] = "o4syncauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_coordinator"
_NEW_COLUMN = "sync_bearer_token"
_COLUMN_TYPE = sa.Text()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _TABLE not in set(inspector.get_table_names()):
        return

    existing = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _NEW_COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_NEW_COLUMN, _COLUMN_TYPE, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    existing = {col["name"] for col in inspector.get_columns(_TABLE)}
    if _NEW_COLUMN in existing:
        op.drop_column(_TABLE, _NEW_COLUMN)
