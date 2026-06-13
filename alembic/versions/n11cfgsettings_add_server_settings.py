"""Add server_configuration.settings (Phase 13.1.H config classification).

Adds a JSON ``settings`` key/value bag to the ``server_configuration``
singleton to hold server-scoped runtime options migrated out of
``sysmanage.yaml`` (jwt timeouts, message-queue tunables, monitoring,
etc.).  The config layer reads this first and falls back to YAML with a
deprecation warning — see docs/planning/config-classification.md and
backend/config/settings_service.py.

Additive, idempotent, identical on SQLite + PostgreSQL.

Revision ID: n11cfgsettings
Revises: m10fedseclease
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n11cfgsettings"
down_revision: Union[str, None] = "m10fedseclease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "server_configuration"
_COLUMN = "settings"


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
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COLUMN):
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
