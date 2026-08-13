# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host.available_packages_fingerprint — skip re-sending an unchanged catalog

The available-packages catalog is ~89k rows / ~11 MB per host and changes
rarely, yet it was retransmitted in full every collection cycle because neither
side had any way to say "I already have exactly this".

Storing the fingerprint the host last delivered lets the server hand it back in
the ``collect_available_packages`` command it already sends, so the agent can
compare and skip.  Deliberately carried on the COMMAND rather than as a reply:
``route_inbound_message`` discards handler return values, so the server has no
working path to answer an agent mid-exchange (see the 9.4 GB incident, where
1,023 payload messages were shipped into a batch the server had already
rejected and never got to say so).

NULL means "we hold nothing from this host", which makes the agent send
unconditionally -- the safe direction, and what every existing row gets.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: x3pkgfp
Revises: x2pkghost
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "x3pkgfp"
down_revision: Union[str, None] = "x2pkghost"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMNS = {
    "available_packages_fingerprint": sa.String(length=64),
    "available_packages_fingerprint_at": sa.DateTime(),
}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype in _COLUMNS.items():
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
