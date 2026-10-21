# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""software_package.revision: 50 -> 255 characters (2026-10-21)

Tenant data.  The column was sized for snap revision numbers (Phase 17.1),
but container-image packages ("oci") record their image digest there, and a
sha256 digest is 71 characters (``sha256:`` + 64 hex; sha512 would be 135).
One such row failed the whole host's software inventory insert on
PostgreSQL ("value too long for type character varying(50)"), so the host's
package list silently stopped updating (t14, 2026-10-21).

Widening only.  Idempotent: a column already 255 or wider is left alone.
Safe on SQLite + PostgreSQL.

Revision ID: q52pkgrevision
Revises: q51backupdu
"""

from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "q52pkgrevision"
down_revision: Union[str, None] = "q51backupdu"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "software_package"
_COLUMN = "revision"
_WIDTH = 255


def _current_length():
    insp = sa.inspect(op.get_bind())
    if _TABLE not in set(insp.get_table_names()):
        return None
    for column in insp.get_columns(_TABLE):
        if column["name"] == _COLUMN:
            return getattr(column["type"], "length", None) or 0
    return None


def upgrade() -> None:
    length = _current_length()
    if length is None or length >= _WIDTH:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            _COLUMN,
            existing_type=sa.String(length),
            type_=sa.String(_WIDTH),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Not narrowed back: a digest already stored would not fit.
    pass
