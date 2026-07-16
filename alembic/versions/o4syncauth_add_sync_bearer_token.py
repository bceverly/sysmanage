# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_sync_bearer_token

Phase 12.6: federation wire protocol — bearer-token auth for site
→ coordinator HTTP push.

Adds one nullable column to ``federation_sites``:

  ``sync_bearer_token_hash``  — SHA-256 of the long-lived bearer
                                token the site presents on every
                                inbound sync POST.  NULL until
                                ``complete_enrollment`` mints one
                                (or after ``regenerate_sync_bearer_token``
                                rotates it).  Plaintext is returned
                                once at enrollment-complete time and
                                stored by the site server in its
                                ``federation_coordinator`` row; the
                                coordinator never persists the
                                plaintext.

mTLS hardening is deferred to a follow-up slice — bearer-over-TLS
is sufficient for v1 of the transport.

Idempotent + cross-dialect (SQLite + PostgreSQL): guards on the
column-exists check before adding.

Revision ID: o4syncauth
Revises: n3regkey12d
Create Date: 2026-05-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "o4syncauth"
down_revision: Union[str, None] = "n3regkey12d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_sites"
_NEW_COLUMN = "sync_bearer_token_hash"
_COLUMN_TYPE = sa.String(128)


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
