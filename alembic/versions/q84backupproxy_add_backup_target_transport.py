# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""restate-proxy: how hosts reach a target's storage (ROADMAP 25.5).

``backup_target.transport`` is ``nfs`` (every target until now, unchanged) or
``proxy``: the storage host runs ``restate-proxy`` and hosts reach their
repositories over HTTPS at ``proxy_host:proxy_port``, trusting its
certificate through the system store, a site CA (``proxy_ca_pem``) or a
pinned key (``proxy_pin_sha256``).  The repositories stay where they are, so
a target can be switched either way.  ``proxy_clients`` is the list of
clients the storage host's grants were last built for.

Each host makes its own proxy tokens and reports only their SHA-256, which
``backup_policy`` keeps: ``proxy_token_sha256`` for the current repository,
``proxy_token_sha256_old`` while a rotation is under way (the grant names
both), and ``proxy_previous_token_sha256`` for the repository before Pro+
encryption.  The tokens themselves never leave the host.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q84backupproxy
Revises: q83escrowkeyref
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q84backupproxy"
down_revision: Union[str, None] = "q83escrowkeyref"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TARGET = "backup_target"
_POLICY = "backup_policy"
_TARGET_COLUMNS = (
    sa.Column("transport", sa.String(16), nullable=False, server_default="nfs"),
    sa.Column("proxy_host", sa.String(255), nullable=True),
    sa.Column("proxy_port", sa.Integer(), nullable=True),
    sa.Column("proxy_pin_sha256", sa.String(64), nullable=True),
    sa.Column("proxy_ca_pem", sa.Text(), nullable=True),
    # The clients the storage host was last given (JSON): the backup tick
    # re-sends the grants when a host joins, leaves or is deleted.
    sa.Column("proxy_clients", sa.Text(), nullable=True),
)
_POLICY_COLUMNS = (
    sa.Column("proxy_token_sha256", sa.String(64), nullable=True),
    sa.Column("proxy_token_sha256_old", sa.String(64), nullable=True),
    sa.Column("proxy_previous_token_sha256", sa.String(64), nullable=True),
)


def _add(inspector, table: str, columns) -> None:
    have = {c["name"] for c in inspector.get_columns(table)}
    for column in columns:
        if column.name not in have:
            op.add_column(table, column.copy())


def _drop(inspector, table: str, columns) -> None:
    have = {c["name"] for c in inspector.get_columns(table)}
    names = [c.name for c in columns if c.name in have]
    if names:
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.drop_column(name)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if _TARGET not in tables:
        return  # the bootstrap database: no tenant tables
    _add(inspector, _TARGET, _TARGET_COLUMNS)
    _add(inspector, _POLICY, _POLICY_COLUMNS)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if _TARGET not in tables:
        return
    _drop(inspector, _POLICY, _POLICY_COLUMNS)
    _drop(inspector, _TARGET, _TARGET_COLUMNS)
