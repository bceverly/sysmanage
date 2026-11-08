# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Hosts behind NAT, said plainly (ROADMAP 25.8).

A host on a private network behind another reaches the storage host's NFS
port, so the reach check passed, but the storage host sees its traffic come
from the gateway and refuses the mount its export made for the host's own
address.  The reach check now holds its connection open and reports its
source port, and the storage host's agent lists who it sees on port 2049;
four columns on ``backup_reach`` carry that:

* ``local_port`` -- the source port of the host's held connection;
* ``peers_command_id`` -- the storage host's ``list_nfs_peers`` answering it;
* ``seen_as`` -- the address the storage host saw that connection come from,
  when it is not the one the export names (None: not behind NAT, or unknown);
* ``nat_checked_at`` -- when the storage host's answer came.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q81reachnat
Revises: q80hostcertmtls
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q81reachnat"
down_revision: Union[str, None] = "q80hostcertmtls"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "backup_reach"
_COLUMNS = (
    ("local_port", sa.Integer()),
    ("peers_command_id", sa.String(36)),
    ("seen_as", sa.String(255)),
    ("nat_checked_at", sa.DateTime()),
)
_INDEX = "ix_backup_reach_peers_command_id"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, column_type in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, column_type, nullable=True))
    if _INDEX not in {i["name"] for i in inspect(op.get_bind()).get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["peers_command_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    if _INDEX in {i["name"] for i in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)
    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name in reversed([column[0] for column in _COLUMNS]):
            if name in existing:
                batch.drop_column(name)
