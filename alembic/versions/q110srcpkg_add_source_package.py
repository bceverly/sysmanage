# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``software_package.source_package``: the source package each installed
package was built from (Debian's ``${source:Package}``, an RPM's SOURCERPM
name, Alpine's origin).

Debian, Fedora and Alpine advisories name SOURCE packages (``openssl``) while
hosts install binaries (``libssl3``, ``openssl-libs``, ``libcrypto3``), so an
advisory can only be matched to a host through this.  Additive only;
idempotent and identical on SQLite and PostgreSQL.

Revision ID: q110srcpkg
Revises: q109softuserfks
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "q110srcpkg"
down_revision: Union[str, None] = "q109softuserfks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE, COLUMN = "software_package", "source_package"


def _columns():
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return None
    return {column["name"] for column in inspector.get_columns(TABLE)}


def upgrade() -> None:
    columns = _columns()
    if columns is not None and COLUMN not in columns:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(255), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if columns is not None and COLUMN in columns:
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
