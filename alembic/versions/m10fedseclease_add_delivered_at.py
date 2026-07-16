# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add federation_secret_lease.delivered_at (Phase 12.5 lease rotation/delivery).

The coordinator now delivers an issued/rotated secret's transient value to the
requesting site in the same reconcile pass that produces it.  ``delivered_at``
records a successful delivery; a NULL on an ``active`` lease means "still needs
delivery", which the reconcile rotation pass retries (rotating the credential
and re-delivering) so a site that was offline at issue time receives a fresh
value when it returns.

Additive, idempotent, identical on SQLite + PostgreSQL.

Revision ID: m10fedseclease
Revises: m9fedid
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m10fedseclease"
down_revision: Union[str, None] = "m9fedid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "federation_secret_lease"
_COLUMN = "delivered_at"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in set(inspector.get_table_names()) and not _has_column(
        inspector, _TABLE, _COLUMN
    ):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
