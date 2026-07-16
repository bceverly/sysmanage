# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Rename server_configuration.server_role -> air_gap_role.

Phase 12 added a second role axis (``federation_role``).  With both columns
side by side, ``server_role`` was ambiguous — it has only ever meant the
*air-gap* topology role (standard/collector/repository).  Rename it to
``air_gap_role`` so the schema reads clearly alongside ``federation_role``.

Idempotent + cross-backend (SQLite + PostgreSQL): the rename only runs when
the old column is present and the new one isn't, so re-running — or running
against a fresh DB that already has ``air_gap_role`` from the model — is a
no-op.  Uses batch_alter_table so SQLite (no native multi-op ALTER) and
PostgreSQL both work.

Revision ID: n8agrole
Revises: m7fedrole
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n8agrole"
down_revision: Union[str, None] = "m7fedrole"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "server_configuration"
_OLD = "server_role"
_NEW = "air_gap_role"


def _columns(inspector) -> set:
    if _TABLE not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def _rename(from_col: str, to_col: str) -> None:
    bind = op.get_bind()
    cols = _columns(sa.inspect(bind))
    # Only act when the source exists and the target doesn't — makes the
    # migration safe to re-run and a no-op on a fresh model-created DB.
    if from_col not in cols or to_col in cols:
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.alter_column(
            from_col,
            new_column_name=to_col,
            existing_type=sa.String(40),
            existing_nullable=False,
        )


def upgrade() -> None:
    _rename(_OLD, _NEW)


def downgrade() -> None:
    _rename(_NEW, _OLD)
