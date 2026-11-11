# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy's certificate, issued by the SysManage CA (ROADMAP 25.5).

``backup_target.proxy_cert_pem``: the TLS certificate the server signed for the
target's restate-proxy, from the storage host's own request -- the storage
host makes the key and it never leaves it.  It names ``proxy_host`` and is
renewed the same way before it expires; hosts trust it through the SysManage
CA, sent as the target's CA.  A certificate, not a secret.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q85proxycert
Revises: q84backupproxy
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q85proxycert"
down_revision: Union[str, None] = "q84backupproxy"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TARGET = "backup_target"
_COLUMN = "proxy_cert_pem"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TARGET not in inspector.get_table_names():
        return  # the bootstrap database: no tenant tables
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_TARGET)}:
        op.add_column(_TARGET, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TARGET not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_TARGET)}:
        with op.batch_alter_table(_TARGET) as batch:
            batch.drop_column(_COLUMN)
