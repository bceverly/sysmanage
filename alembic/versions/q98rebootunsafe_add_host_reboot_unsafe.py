# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Not safe to reboot (2026-11-19).

Production, 2026-11-19: an "update all" left three hosts with a
half-configured kernel and no initramfs, and "reboot required" -- a reboot
would have booted a kernel that could not start.  The agent now reports with
its package manager health whether a reboot is safe, and every reboot path
refuses while it is not.

``host.reboot_unsafe`` and ``host.reboot_unsafe_reason`` (the agent's words).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q98rebootunsafe
Revises: q97fedbackuprollup
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q98rebootunsafe"
down_revision: Union[str, None] = "q97fedbackuprollup"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST = "host"
_COLUMNS = (
    ("reboot_unsafe", lambda: sa.Column(
        "reboot_unsafe", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("reboot_unsafe_reason", lambda: sa.Column(
        "reboot_unsafe_reason", sa.String(255), nullable=True)),
)  # fmt: skip


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _HOST not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_HOST)}
    for name, column in _COLUMNS:
        if name not in have:
            op.add_column(_HOST, column())


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _HOST not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(_HOST)}
    drop = [name for name, _column in _COLUMNS if name in have]
    if drop:
        with op.batch_alter_table(_HOST) as batch:
            for name in drop:
                batch.drop_column(name)
