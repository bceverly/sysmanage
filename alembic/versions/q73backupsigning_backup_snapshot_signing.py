# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Snapshot signing (Pro+ backup_engine, ROADMAP 24.6, 2026-11-02)

Tenant data.  ``backup_target`` gains the snapshot signer's key: its public
half (sent to every backed-up host as ``trusted_key``), fingerprint, the
OpenBAO reference of its secret half (released to the storage host for one
sign job at a time; never stored here) and when signing was turned on.
``backup_snapshot`` gains ``signer``: the fingerprint restate reported when
it signed (``signed`` already exists).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q73backupsigning
Revises: q72scriptapproval
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q73backupsigning"
down_revision: Union[str, None] = "q72scriptapproval"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TARGET_COLUMNS = (
    ("sign_public_key", sa.Text()),
    ("sign_fingerprint", sa.String(64)),
    ("sign_key_ref", sa.String(512)),
    ("signing_enabled_at", sa.DateTime()),
)
_SNAPSHOT_COLUMNS = (("signer", sa.String(64)),)


def _columns(table):
    insp = inspect(op.get_bind())
    if table not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns(table)}


def _add(table, wanted):
    present = _columns(table)
    if present is None:
        return
    for name, kind in wanted:
        if name not in present:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def _drop(table, wanted):
    present = _columns(table)
    if present is None:
        return
    names = [name for name, _kind in wanted if name in present]
    if names:
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.drop_column(name)


def upgrade() -> None:
    _add("backup_target", _TARGET_COLUMNS)
    _add("backup_snapshot", _SNAPSHOT_COLUMNS)


def downgrade() -> None:
    _drop("backup_snapshot", _SNAPSHOT_COLUMNS)
    _drop("backup_target", _TARGET_COLUMNS)
