# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet restore hosts in the order they were listed (2026-11-25).

``backup_fleet_restore_target.position``: where the host was in the job's
list.  Hosts were released ordered by their random row ids, so a job listing
its most important hosts first restored them in no particular order (lab
run, 2026-11-25).  Rows from before this have no position and go after the
numbered ones, by id as before.  Pure additive nullable column; idempotent
and identical on SQLite and PostgreSQL.

Revision ID: q116fleetorder
Revises: q115dispatchcorr
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "q116fleetorder"
down_revision: Union[str, None] = "q115dispatchcorr"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_fleet_restore_target"
_COLUMN = "position"


def _columns():
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns is None or _COLUMN in columns:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if columns is not None and _COLUMN in columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)  # expand-contract-ok: downgrade only
