# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``shared_advisory_package.affected_from``: the first version an advisory
affects, where the feed says.

FreeBSD's VuXML gives ranges -- ``<ge>8.1</ge><lt>8.1.4.1</lt>`` affects only
the 8.1 branch -- and without the lower bound a host still on 8.0 read as
needing the 8.1 fix.  Additive only; idempotent and identical on SQLite and
PostgreSQL.

Revision ID: s20advfrom
Revises: s19alpinemirror
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "s20advfrom"
down_revision: Union[str, None] = "s19alpinemirror"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE, COLUMN = "shared_advisory_package", "affected_from"


def _columns():
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return None
    return {column["name"] for column in inspector.get_columns(TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns is not None and COLUMN not in columns:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(100), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if columns is not None and COLUMN in columns:
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
