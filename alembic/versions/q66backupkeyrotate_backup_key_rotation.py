# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: encryption key rotation (Pro+ backup_engine 24.6 S5, 2026-10-27)

Tenant data.  Rotating a policy's key makes a NEW, independent key pair:
new captures are encrypted only to it, and a restore is given every key the
policy has held (a capture after a rotation reuses packs written before
it).  ``backup_policy_key`` is that history, one row per key: its
fingerprint and the OpenBAO reference of its secret key -- never the key
itself -- with when it was made, replaced by the next, and (later, once
restate can say no pack needs it) retired.  ``backup_policy.encrypt_rotated_at``
is when the current key was made by a rotation; ``backup_target.
key_rotation_days`` how often the engine rotates on its own (NULL = the
default, 365; 0 = never).  A policy encrypted before this revision gets its
one key as the first row.  Community never sets any of them.  Additive,
idempotent; safe on SQLite + PostgreSQL.

Why separate key pairs and not encryption subkeys of one key: with GnuPG
2.4.8 and libgcrypt 1.12.0 one gpg-agent can only ever use ONE encryption
subkey of a key, so snapshots from before a rotation could not be restored
(checked on gdr-t14, 2026-10-27).  Separate keys each work.

Revision ID: q66backupkeyrotate
Revises: q65backupequip
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q66backupkeyrotate"
down_revision: Union[str, None] = "q65backupequip"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLE = "backup_policy_key"
_POLICY = (("encrypt_rotated_at", sa.DateTime()),)
_TARGET = (("key_rotation_days", sa.Integer()),)


def _add(insp, table, columns) -> None:
    if table not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns(table)}
    for name, kind in columns:
        if name not in present:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def _drop(insp, table, columns) -> None:
    if table not in set(insp.get_table_names()):
        return
    present = {c["name"] for c in insp.get_columns(table)}
    drop = [name for name, _kind in columns if name in present]
    if drop:
        with op.batch_alter_table(table) as batch:
            for name in drop:
                batch.drop_column(name)


def _create_table(insp) -> None:
    if TABLE in set(insp.get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "policy_id",
            GUID(),
            sa.ForeignKey("backup_policy.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("key_ref", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("replaced_at", sa.DateTime(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
    )


def _backfill() -> None:
    """A policy encrypted before this revision: its one key becomes the
    first row (skipped when the policy already has one)."""
    bind = op.get_bind()
    keys = sa.table(
        TABLE,
        sa.column("id", GUID()),
        sa.column("policy_id", GUID()),
        sa.column("fingerprint", sa.String),
        sa.column("key_ref", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    policies = sa.table(
        "backup_policy",
        sa.column("id", GUID()),
        sa.column("encrypt_fingerprint", sa.String),
        sa.column("encrypt_key_ref", sa.String),
        sa.column("encrypted_at", sa.DateTime),
    )
    have = {str(row[0]) for row in bind.execute(sa.select(keys.c.policy_id))}
    rows = bind.execute(
        sa.select(
            policies.c.id,
            policies.c.encrypt_fingerprint,
            policies.c.encrypt_key_ref,
            policies.c.encrypted_at,
        ).where(policies.c.encrypt_key_ref.isnot(None))
    ).fetchall()
    add = [
        {
            "id": uuid.uuid4(),
            "policy_id": policy_id,
            "fingerprint": fingerprint or "",
            "key_ref": key_ref,
            "created_at": encrypted_at,
        }
        for policy_id, fingerprint, key_ref, encrypted_at in rows
        if str(policy_id) not in have and encrypted_at is not None
    ]
    if add:
        op.bulk_insert(keys, add)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add(insp, "backup_policy", _POLICY)
    _add(insp, "backup_target", _TARGET)
    if "backup_policy" in set(insp.get_table_names()):
        _create_table(insp)
        _backfill()


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if TABLE in set(insp.get_table_names()):
        op.drop_table(TABLE)
    _drop(insp, "backup_target", _TARGET)
    _drop(insp, "backup_policy", _POLICY)
