# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add out-of-band Ed25519 identity-key pinning columns (Phase 12 strict trust).

Strict-by-default enrollment requires each party to prove its identity with an
Ed25519 key whose public half was exchanged OUT OF BAND, defeating an
enrollment-time MITM that a network-fetched TLS cert + bearer token cannot.

  * ``federation_sites.site_identity_public_key_pem`` — the site's identity
    public key, pasted in when the coordinator creates the site row; the
    coordinator verifies the site's enrollment proof against it.
  * ``federation_coordinator.coordinator_identity_public_key_pem`` — the
    coordinator's identity public key, pasted in on the site before enrolling;
    the site verifies the coordinator's enrollment proof against it.

Both nullable Text, additive, idempotent, identical on SQLite + PostgreSQL.

Revision ID: m9fedid
Revises: n8agrole
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m9fedid"
down_revision: Union[str, None] = "n8agrole"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("federation_sites", "site_identity_public_key_pem"),
    ("federation_coordinator", "coordinator_identity_public_key_pem"),
)


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in _COLUMNS:
        if table in set(inspector.get_table_names()) and not _has_column(
            inspector, table, column
        ):
            op.add_column(table, sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in _COLUMNS:
        if _has_column(inspector, table, column):
            op.drop_column(table, column)
