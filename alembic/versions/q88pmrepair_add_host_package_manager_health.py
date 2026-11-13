# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Package manager needs repair (2026-11-13).

Production, 2026-11-13: eight hosts were left with dpkg interrupted, and
every update sent to them failed while they looked healthy.  Each update
scan now reports whether the host's package manager can install anything;
the hosts grid flags it, "Repair package manager" fixes it, and an alert can
watch for it.

``host.package_manager_name`` (dpkg, dnf, pkg -- what was checked),
``package_manager_needs_repair``, ``package_manager_repair_reason`` (the
package manager's own words), ``package_manager_repairable`` (whether the
agent can repair it: dnf's problems are reported, not repaired) and
``package_manager_checked_at``.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q88pmrepair
Revises: q87tokennext
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q88pmrepair"
down_revision: Union[str, None] = "q87tokennext"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST = "host"
_COLUMNS = (
    ("package_manager_name", lambda: sa.Column("package_manager_name", sa.String(16), nullable=True)),
    ("package_manager_needs_repair", lambda: sa.Column(
        "package_manager_needs_repair", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("package_manager_repair_reason", lambda: sa.Column(
        "package_manager_repair_reason", sa.String(255), nullable=True)),
    ("package_manager_repairable", lambda: sa.Column(
        "package_manager_repairable", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("package_manager_checked_at", lambda: sa.Column(
        "package_manager_checked_at", sa.DateTime(), nullable=True)),
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
