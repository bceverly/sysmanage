"""Add federation_role to server_configuration (Phase 12 — Server Role UI).

The federation role (none/coordinator/site) moves into the
``server_configuration`` DB singleton — set via Settings → Server Role —
exactly like the air-gap ``server_role``.  It is an INDEPENDENT axis, so a
single column added alongside ``server_role``.  Additive, idempotent,
identical on SQLite + PostgreSQL.

Revision ID: m7fedrole
Revises: m6fedsecret
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m7fedrole"
down_revision: Union[str, None] = "m6fedsecret"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "server_configuration"
_COLUMN = "federation_role"


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in set(inspector.get_table_names()):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, _TABLE, _COLUMN):
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(40),
                nullable=False,
                server_default="none",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
