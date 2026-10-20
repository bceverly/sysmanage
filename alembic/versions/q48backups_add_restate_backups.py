# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""fleet backup with restate (ROADMAP Phase 24, Community scope)

Tenant data: ``backup_target`` (where repositories live, and how the storage
side seals them), ``backup_policy`` (one per host: schedule, retention, check
cadence, quiesce), ``backup_run`` (every job sent, keyed by the run id the
agent echoes) and ``backup_snapshot`` (each repository's snapshots).

Roles, in the bootstrap database: "Manage Backups" (targets, policies,
back up now) and "Restore Files" (granted apart: a restore puts files back on
a host), granted to administrators and to every operator who already holds
every other role (``backend.persistence.role_grants``).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q48backups
Revises: q47hwtemplimit
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID
from backend.persistence.role_grants import grant_new_role_to_full_holders

revision: str = "q48backups"
down_revision: Union[str, None] = "q47hwtemplimit"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"
_ROLES = (
    ("Manage Backups", "Set backup targets and policies and run backups"),
    ("Restore Files", "Restore files from a backup snapshot"),
)
_ROLE_NAMES = tuple(name for name, _description in _ROLES)

_INDEXES = (
    ("backup_target", "ix_backup_target_storage_host_id", ["storage_host_id"], False),
    ("backup_policy", "ix_backup_policy_host_id", ["host_id"], True),
    ("backup_run", "ix_backup_run_policy_id", ["policy_id"], False),
    ("backup_run", "ix_backup_run_host_id", ["host_id"], False),
    ("backup_run", "ix_backup_run_status", ["status"], False),
    ("backup_run", "ix_backup_run_command_id", ["command_id"], False),
    ("backup_snapshot", "ix_backup_snapshot_policy_id", ["policy_id"], False),
    ("backup_snapshot", "ix_backup_snapshot_host_id", ["host_id"], False),
)


def _fk(table: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{table}.id", ondelete="CASCADE")


def _target() -> None:
    op.create_table(
        "backup_target",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host_mount_point", sa.String(1024), nullable=False),
        sa.Column("storage_host_id", GUID(), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("max_concurrent", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("seal_mode", sa.String(16), nullable=False, server_default="none"),
        sa.Column("zfs_dataset", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _policy() -> None:
    op.create_table(
        "backup_policy",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), _fk("host"), nullable=False),
        sa.Column("target_id", GUID(), _fk("backup_target"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("window_start_hour", sa.Integer(), nullable=True),
        sa.Column("keep_last", sa.Integer(), nullable=False, server_default="14"),
        sa.Column(
            "check_interval_days", sa.Integer(), nullable=False, server_default="7"
        ),
        sa.Column("quiesce", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("quiesce_with", sa.Text(), nullable=True),
        sa.Column("estimate_bytes", sa.BigInteger(), nullable=True),
        sa.Column("repository_bytes", sa.BigInteger(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "host_acked_version", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "storage_acked_version", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("restate_version", sa.String(64), nullable=True),
        sa.Column("storage_restate_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _run() -> None:
    op.create_table(
        "backup_run",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("policy_id", GUID(), _fk("backup_policy"), nullable=False),
        sa.Column("host_id", GUID(), _fk("host"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.String(255), nullable=True),
        sa.Column("progress", sa.Text(), nullable=True),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.Column("restate_version", sa.String(64), nullable=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("command_id", sa.String(64), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=True),
    )


def _snapshot() -> None:
    op.create_table(
        "backup_snapshot",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("policy_id", GUID(), _fk("backup_policy"), nullable=False),
        sa.Column("host_id", GUID(), _fk("host"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("new_bytes", sa.BigInteger(), nullable=True),
        sa.Column("unique_bytes", sa.BigInteger(), nullable=True),
        sa.Column("files", sa.BigInteger(), nullable=True),
        sa.Column("signed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seen_at", sa.DateTime(), nullable=False),
        sa.Column("gone_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("policy_id", "name", name="uq_backup_snapshot_name"),
    )


_TABLES = (
    ("backup_target", _target),
    ("backup_policy", _policy),
    ("backup_run", _run),
    ("backup_snapshot", _snapshot),
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
