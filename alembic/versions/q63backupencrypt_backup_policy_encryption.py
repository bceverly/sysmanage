# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: encrypted repositories (Pro+ backup_engine, 2026-10-25)

Tenant data.  An encrypted repository is a new one beside the old (restate
cannot convert a repository in place), so a policy records its repository
directory when it is not the default, the one before it (still restorable)
and where that one is exported; the public key and fingerprint of its
OpenPGP key pair, and the OpenBAO reference of the secret key -- never the
secret key itself.  ``backup_snapshot.repository_dir`` says which repository
holds each snapshot (NULL = the default).  Community never sets any of
them.  Additive, idempotent; safe on SQLite + PostgreSQL.

Revision ID: q63backupencrypt
Revises: q62backupestdirs
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q63backupencrypt"
down_revision: Union[str, None] = "q62backupestdirs"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_POLICY = (
    ("repository_dir", sa.String(255)),
    ("previous_repository_dir", sa.String(255)),
    ("previous_nfs_path", sa.String(1024)),
    ("encrypt_public_key", sa.Text()),
    ("encrypt_fingerprint", sa.String(64)),
    ("encrypt_key_ref", sa.String(1024)),
    ("encrypted_at", sa.DateTime()),
)
_SNAPSHOT = (("repository_dir", sa.String(255)),)


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


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _add(insp, "backup_policy", _POLICY)
    _add(insp, "backup_snapshot", _SNAPSHOT)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    _drop(insp, "backup_snapshot", _SNAPSHOT)
    _drop(insp, "backup_policy", _POLICY)
