# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Host certificate tracking for agent mutual TLS (ROADMAP 25.10).

Agents now get their client certificate by sending a certificate request
over their authenticated channel, renew it before it expires, and present it
on every connection.  Three columns on ``host`` support that:

* ``certificate_expires_at`` -- when the current certificate expires, so the
  Hosts list can show hosts near expiry without parsing every PEM;
* ``certificate_last_presented_at`` -- the last time a connection presented
  a valid certificate for this host, which is how the Hosts list shows hosts
  not yet presenting one (before enforcement is turned on);
* ``previous_certificate_serial`` -- the serial replaced by the last renewal,
  accepted for a day so a connection opened just before a renewal is not
  refused.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q80hostcertmtls
Revises: q79cloudnodelete
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q80hostcertmtls"
down_revision: Union[str, None] = "q79cloudnodelete"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMNS = (
    ("certificate_expires_at", sa.DateTime()),
    ("certificate_last_presented_at", sa.DateTime()),
    ("previous_certificate_serial", sa.String(64)),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, column_type in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name in reversed([column[0] for column in _COLUMNS]):
            if name in existing:
                batch.drop_column(name)
