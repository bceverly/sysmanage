# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic update policies (ROADMAP 26.1, Enterprise).

* ``upgrade_profiles``: ``auto_apply`` (off), ``reboot_mode`` (never),
  ``excluded_packages``, ``require_backup_hours``, and the per-policy hold
  (``held``, ``hold_reason``, ``hold_by``, ``hold_at``)
* ``upgrade_profile_host``: the hosts a policy lists by name
* ``auto_update_settings``: the tenant's hold on every policy, retry hours,
  reboot timeout (one row, made on first use)
* ``auto_update_run``: one policy firing on one host
* ``host.auto_update_opt_out`` / ``auto_update_opt_out_reason``; ``host.boot_time``
* ``package_update.held``: pinned on the host, never applied automatically
* ``update_execution_log.run_id``: the automatic run that queued it

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q94autoupdate
Revises: q93newdevicealert
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q94autoupdate"
down_revision: Union[str, None] = "q93newdevicealert"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _columns():
    return {
        "upgrade_profiles": [
            sa.Column(
                "auto_apply", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "reboot_mode", sa.String(16), nullable=False, server_default="never"
            ),
            sa.Column("excluded_packages", sa.Text(), nullable=True),
            sa.Column("require_backup_hours", sa.Integer(), nullable=True),
            sa.Column("held", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("hold_reason", sa.String(1000), nullable=True),
            sa.Column("hold_by", sa.String(255), nullable=True),
            sa.Column("hold_at", sa.DateTime(), nullable=True),
        ],
        "host": [
            sa.Column(
                "auto_update_opt_out",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("auto_update_opt_out_reason", sa.String(1000), nullable=True),
            sa.Column("boot_time", sa.DateTime(), nullable=True),
        ],
        "package_update": [
            sa.Column("held", sa.Boolean(), nullable=False, server_default=sa.false()),
        ],
        "update_execution_log": [
            sa.Column("run_id", GUID(), nullable=True),
        ],
    }


def _tables():
    return {
        "upgrade_profile_host": [
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "profile_id",
                GUID(),
                sa.ForeignKey("upgrade_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "profile_id", "host_id", name="uq_upgrade_profile_host"
            ),
        ],
        "auto_update_settings": [
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "hold_all", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("hold_reason", sa.String(1000), nullable=True),
            sa.Column("hold_by", sa.String(255), nullable=True),
            sa.Column("hold_at", sa.DateTime(), nullable=True),
            sa.Column(
                "retry_after_hours", sa.Integer(), nullable=False, server_default="24"
            ),
            sa.Column(
                "reboot_timeout_minutes",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        ],
        "auto_update_run": [
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "profile_id",
                GUID(),
                sa.ForeignKey("upgrade_profiles.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("profile_name", sa.String(120), nullable=False),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("reason", sa.String(40), nullable=True),
            sa.Column("triggered_by", sa.String(255), nullable=True),
            sa.Column("packages", sa.JSON(), nullable=True),
            sa.Column("skipped", sa.JSON(), nullable=True),
            sa.Column(
                "applied_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failures", sa.JSON(), nullable=True),
            sa.Column(
                "reboot_needed", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "reboot_status", sa.String(12), nullable=False, server_default="none"
            ),
            sa.Column("reboot_queued_at", sa.DateTime(), nullable=True),
            sa.Column("reboot_back_at", sa.DateTime(), nullable=True),
            sa.Column("command_id", sa.String(36), nullable=True),
            sa.Column("queued_at", sa.DateTime(), nullable=False),
            sa.Column("release_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("acknowledged_by", sa.String(255), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        ],
    }


_INDEXES = (
    ("upgrade_profile_host", "ix_upgrade_profile_host_profile_id", ["profile_id"]),
    ("upgrade_profile_host", "ix_upgrade_profile_host_host_id", ["host_id"]),
    ("auto_update_run", "ix_auto_update_run_profile_id", ["profile_id"]),
    ("auto_update_run", "ix_auto_update_run_host_id", ["host_id"]),
    ("auto_update_run", "ix_auto_update_run_status", ["status"]),
    ("auto_update_run", "ix_auto_update_run_command_id", ["command_id"]),
    ("auto_update_run", "ix_auto_update_run_queued_at", ["queued_at"]),
    ("update_execution_log", "ix_update_execution_log_run_id", ["run_id"]),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in have:
                op.add_column(table, column)
    for table, columns in _tables().items():
        if table not in tables:
            op.create_table(table, *columns)
    inspector = inspect(op.get_bind())
    for table, name, cols in _INDEXES:
        if table in inspector.get_table_names():
            if name not in {i["name"] for i in inspector.get_indexes(table)}:
                op.create_index(name, table, cols)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, name, _cols in _INDEXES:
        if table in tables and name in {
            i["name"] for i in inspector.get_indexes(table)
        }:
            op.drop_index(name, table_name=table)
    for table in ("auto_update_run", "auto_update_settings", "upgrade_profile_host"):
        if table in tables:
            op.drop_table(table)
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name in have:
                    batch.drop_column(column.name)
