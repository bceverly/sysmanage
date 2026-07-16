# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add livepatch columns to ubuntu_pro_info (Phase 13.3 — Livepatch Integration)

Adds Canonical Livepatch detail columns reported by the agent (from
``canonical-livepatch status``) when the livepatch Ubuntu Pro service is
enabled.  All nullable / defaulted so existing rows and non-livepatch hosts are
unaffected.

Idempotent (per-column guard); safe on SQLite + PostgreSQL.

Revision ID: k1livepatch
Revises: j1killproc
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "k1livepatch"
down_revision: Union[str, None] = "j1killproc"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "ubuntu_pro_info"

_COLUMNS = [
    (
        "livepatch_enabled",
        sa.Column(
            "livepatch_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    ),
    (
        "livepatch_client_version",
        sa.Column("livepatch_client_version", sa.String(length=50), nullable=True),
    ),
    (
        "livepatch_patch_state",
        sa.Column("livepatch_patch_state", sa.String(length=50), nullable=True),
    ),
    (
        "livepatch_check_state",
        sa.Column("livepatch_check_state", sa.String(length=50), nullable=True),
    ),
    (
        "livepatch_patch_version",
        sa.Column("livepatch_patch_version", sa.String(length=50), nullable=True),
    ),
    (
        "livepatch_kernel",
        sa.Column("livepatch_kernel", sa.String(length=255), nullable=True),
    ),
    (
        "livepatch_last_check",
        sa.Column("livepatch_last_check", sa.DateTime(), nullable=True),
    ),
    ("livepatch_fixes", sa.Column("livepatch_fixes", sa.Text(), nullable=True)),
]


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, column in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, column)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, _column in _COLUMNS:
        if name in existing:
            # expand-contract-ok: reverse of this revision's add_column.
            op.drop_column(_TABLE, name)
