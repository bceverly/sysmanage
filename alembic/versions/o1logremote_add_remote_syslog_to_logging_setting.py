# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add remote-syslog fields to logging_setting (Phase 14.5 — remote log routing)

Adds ``syslog_host`` / ``syslog_port`` / ``syslog_facility`` / ``syslog_protocol``
to ``logging_setting``.  These are only meaningful when
``native_target == 'syslog_remote'`` — forwarding SysManage's own logs to a
remote syslog server, a Professional-gated (``LOG_ROUTING``) capability.  The
existing local sinks (file / journald / local syslog / eventlog) are unchanged
and stay OSS.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: o1logremote
Revises: n1custmetric
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1logremote"
down_revision: Union[str, None] = "n1custmetric"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "logging_setting"
_COLUMNS = (
    ("syslog_host", sa.String(length=255)),
    ("syslog_port", sa.Integer()),
    ("syslog_facility", sa.String(length=20)),
    ("syslog_protocol", sa.String(length=3)),
)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype in _COLUMNS:
        if name not in existing:
            # ADD COLUMN (nullable) is supported natively on SQLite + PostgreSQL.
            op.add_column(_TABLE, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    # expand-contract-ok: reverse of this revision's add_column set.  Batch mode
    # so DROP COLUMN works on SQLite (table-rebuild) as well as PostgreSQL.
    to_drop = [name for name, _ in reversed(_COLUMNS) if name in existing]
    if to_drop:
        with op.batch_alter_table(_TABLE) as batch:
            for name in to_drop:
                batch.drop_column(name)
