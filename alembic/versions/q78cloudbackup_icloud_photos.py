# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""cloud storage to local: iCloud Photos (ROADMAP 24.12, Community)

Tenant data: ``cloud_backup_enable`` (the storage host's "Enable iCloud
backup"), ``cloud_backup_account`` (an Apple ID and library; its password is
in OpenBAO, never here) and ``cloud_backup_run`` (every job sent to the
storage host's agent).

Role, in the bootstrap database: "Manage Cloud Backups" (enable it, add
accounts, enter two-factor codes, run now), granted to administrators and to
every operator who already holds every other role.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q78cloudbackup
Revises: q77ossbackupkeys
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID
from backend.persistence.role_grants import grant_new_role_to_full_holders

revision: str = "q78cloudbackup"
down_revision: Union[str, None] = "q77ossbackupkeys"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"
_ROLES = (
    (
        "Manage Cloud Backups",
        "Download iCloud Photos to the backup storage: add accounts, sign in, run now",
    ),
)
_ROLE_NAMES = tuple(name for name, _description in _ROLES)

_INDEXES = (
    ("cloud_backup_enable", "ix_cloud_backup_enable_target_id", ["target_id"], True),
    ("cloud_backup_account", "ix_cloud_backup_account_target_id", ["target_id"], False),
    ("cloud_backup_run", "ix_cloud_backup_run_target_id", ["target_id"], False),
    ("cloud_backup_run", "ix_cloud_backup_run_account_id", ["account_id"], False),
    ("cloud_backup_run", "ix_cloud_backup_run_status", ["status"], False),
    ("cloud_backup_run", "ix_cloud_backup_run_command_id", ["command_id"], False),
)


def _enable() -> None:
    op.create_table(
        "cloud_backup_enable",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("target_id", GUID(), nullable=False),
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("tool_version", sa.String(32), nullable=True),
        sa.Column("install_method", sa.String(16), nullable=True),
        sa.Column("cloud_root", sa.String(1024), nullable=True),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )


def _account() -> None:
    op.create_table(
        "cloud_backup_account",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("target_id", GUID(), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False, server_default="icloud"),
        sa.Column("apple_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "library", sa.String(255), nullable=False, server_default="PrimarySync"
        ),
        sa.Column("libraries", sa.Text(), nullable=True),
        sa.Column("password_ref", sa.String(512), nullable=True),
        sa.Column("password_set_at", sa.DateTime(), nullable=True),
        sa.Column("dir_name", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("window_start_hour", sa.Integer(), nullable=True),
        sa.Column("until_found", sa.Integer(), nullable=False, server_default="50"),
        sa.Column(
            "auto_delete", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("state", sa.String(16), nullable=False, server_default="new"),
        sa.Column("state_message", sa.Text(), nullable=True),
        sa.Column("session_created_at", sa.DateTime(), nullable=True),
        sa.Column("session_warned_at", sa.DateTime(), nullable=True),
        sa.Column("last_good_at", sa.DateTime(), nullable=True),
        sa.Column("last_full_at", sa.DateTime(), nullable=True),
        sa.Column("photos_local", sa.Integer(), nullable=True),
        sa.Column("bytes_local", sa.BigInteger(), nullable=True),
        sa.Column("run_requested_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def _run() -> None:
    op.create_table(
        "cloud_backup_run",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("target_id", GUID(), nullable=False),
        sa.Column("account_id", GUID(), nullable=True),
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("command_id", sa.String(64), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("progress", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("downloaded", sa.Integer(), nullable=True),
        sa.Column("present", sa.Integer(), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=True),
        sa.Column("bytes_downloaded", sa.BigInteger(), nullable=True),
        sa.Column("password_released_at", sa.DateTime(), nullable=True),
        sa.Column("code_requested_at", sa.DateTime(), nullable=True),
        sa.Column("mfa_code", sa.String(16), nullable=True),
        sa.Column("code_released_at", sa.DateTime(), nullable=True),
    )


_TABLES = (
    ("cloud_backup_enable", _enable),
    ("cloud_backup_account", _account),
    ("cloud_backup_run", _run),
)


def _seed_roles(bind) -> None:
    tables = set(inspect(bind).get_table_names())
    if not {"security_roles", "user_security_roles", "user"} <= tables:
        return  # a tenant database: roles live with the registry
    is_sqlite = bind.dialect.name == "sqlite"
    id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
    gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
    for name, description in _ROLES:
        existing = bind.execute(
            sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
            {"name": name},
        ).scalar()
        if not existing:
            op.execute(
                sa.text(
                    "INSERT INTO security_roles (id, name, description, group_id) "
                    f"VALUES ({id_ph}, :name, :description, {gid_ph})"
                ).bindparams(
                    id=str(uuid.uuid4()),
                    name=name,
                    description=description,
                    group_id=_HOST_GROUP_ID,
                )
            )
    for name in _ROLE_NAMES:
        grant_new_role_to_full_holders(bind, name, new_roles=_ROLE_NAMES)


def upgrade() -> None:
    bind = op.get_bind()
    _seed_roles(bind)
    if "host" not in set(inspect(bind).get_table_names()):
        return
    for table, create in _TABLES:
        if table not in set(inspect(bind).get_table_names()):
            create()
    for table, name, columns, unique in _INDEXES:
        if name not in {ix["name"] for ix in inspect(bind).get_indexes(table)}:
            op.create_index(name, table, columns, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table, _create in reversed(_TABLES):
        if table in tables:
            op.drop_table(table)
    if {"security_roles", "user_security_roles"} <= tables:
        for name in _ROLE_NAMES:
            op.execute(
                sa.text(
                    "DELETE FROM user_security_roles WHERE role_id IN "
                    "(SELECT id FROM security_roles WHERE name = :name)"
                ).bindparams(name=name)
            )
            op.execute(
                sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                    name=name
                )
            )
