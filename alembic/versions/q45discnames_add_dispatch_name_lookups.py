# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""network_discovery_dispatch.name_lookups (device hostnames, 2026-10-17)

Tenant data. Whether each agent was last told it may resolve the names of
devices that announce none (reverse DNS -- active, so it follows the
operator's sweep opt-in). Tracked so the reconciler re-sends the setting when
that opt-in changes. Existing rows start ``false``: the reconciler then sends
``true`` wherever the policy already allows sweeps.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q45discnames
Revises: q44rolegrants
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q45discnames"
down_revision: Union[str, None] = "q44rolegrants"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "network_discovery_dispatch"
_COLUMN = "name_lookups"


def _has_column(insp) -> bool:
    return _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names() and not _has_column(insp):
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if _TABLE in insp.get_table_names() and _has_column(insp):
        with op.batch_alter_table(_TABLE) as batch:
            # expand-contract-ok: reverse of this revision's add_column.
            batch.drop_column(_COLUMN)
