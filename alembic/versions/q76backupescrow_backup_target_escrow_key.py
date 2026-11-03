# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remembered break-glass escrow key (Pro+ backup_engine, ROADMAP 24.6, 2026-11-03)

Tenant data.  ``backup_target`` gains the operator's escrow PUBLIC key -- the
OpenPGP key break-glass exports are sealed to -- with its fingerprint, user id,
and when and by whom it was saved, so the next export defaults to it and the
Encryption panel can say which key the exports are sealed to.  Only the public
half is ever stored (it is not a secret, so it lives here, not in OpenBAO).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q76backupescrow
Revises: q75backuptagpolicy
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q76backupescrow"
down_revision: Union[str, None] = "q75backuptagpolicy"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TARGET_COLUMNS = (
    ("escrow_public_key", sa.Text()),
    ("escrow_fingerprint", sa.String(64)),
    ("escrow_uid", sa.String(255)),
    ("escrow_saved_at", sa.DateTime()),
    ("escrow_saved_by", sa.String(255)),
)


def _columns(table):
    insp = inspect(op.get_bind())
    if table not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    present = _columns("backup_target")
    if present is None:
        return
    for name, kind in _TARGET_COLUMNS:
        if name not in present:
            op.add_column("backup_target", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    present = _columns("backup_target")
    if present is None:
        return
    for name, _kind in reversed(_TARGET_COLUMNS):
        if name in present:
            op.drop_column("backup_target", name)
