# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A host's one-time re-enroll code (2026-11-24).

An agent that lost its database -- a rebuilt or reinstalled host -- is
refused ``host_credential_required`` for good (Phase 22.0: a host is its
token, never its name), and the only way back was to delete the host and
lose its history.  An administrator can now issue a one-time code for the
host; an agent registering under that name with the code takes over the
existing record with a new token.  Only the code's SHA-256 is kept, with
when it expires and who issued it.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q113reenroll
Revises: q112requestkind
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q113reenroll"
down_revision: Union[str, None] = "q112requestkind"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"
_COLUMNS = (
    ("reenroll_code_hash", sa.String(64)),
    ("reenroll_code_expires_at", sa.DateTime()),
    ("reenroll_code_by", sa.String(255)),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, kind in _COLUMNS:
        if name not in have:
            op.add_column(_TABLE, sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE) as batch:
        for name, _kind in reversed(_COLUMNS):
            if name in have:
                batch.drop_column(name)
