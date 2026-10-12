# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add NTP policy tables + host time-service configuration (Phase 23.3 S5b)

``ntp_policy`` (fleet / site / tag servers, enforce, auto-resync),
``ntp_policy_state`` (one row per host: what it was last sent and how that
went), and four host columns for how the host's time service is configured.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q40ntppolicy
Revises: q39clockresync
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q40ntppolicy"
down_revision: Union[str, None] = "q39clockresync"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST_COLUMNS = (
    ("time_configured_servers", sa.Text()),
    ("time_service_enabled", sa.Boolean()),
    ("time_service_unit", sa.String(64)),
    ("time_config_path", sa.String(255)),
)


def upgrade() -> None:
    bind = op.get_bind()
    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    for name, coltype in _HOST_COLUMNS:
        if name not in host_columns:
            op.add_column("host", sa.Column(name, coltype, nullable=True))
    tables = set(inspect(bind).get_table_names())
    if "ntp_policy" not in tables:
        op.create_table(
            "ntp_policy",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("scope_kind", sa.String(16), nullable=False),
            sa.Column("scope_ref", sa.String(64), nullable=False, server_default=""),
            sa.Column("servers", sa.Text(), nullable=False),
            sa.Column(
                "enforce", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "auto_resync", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.String(255), nullable=True),
            sa.UniqueConstraint("scope_kind", "scope_ref", name="uq_ntp_policy_scope"),
        )
    if "ntp_policy_state" not in tables:
        op.create_table(
            "ntp_policy_state",
            sa.Column("host_id", GUID(), primary_key=True),
            sa.Column("policy_digest", sa.String(64), nullable=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("command_id", sa.String(36), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.String(2000), nullable=True),
            sa.Column("auto_resync_at", sa.DateTime(), nullable=True),
        )
    indexes = {ix["name"] for ix in inspect(bind).get_indexes("ntp_policy_state")}
    if "ix_ntp_policy_state_command_id" not in indexes:
        op.create_index(
            "ix_ntp_policy_state_command_id", "ntp_policy_state", ["command_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table in ("ntp_policy_state", "ntp_policy"):
        if table in tables:
            op.drop_table(table)
    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    with op.batch_alter_table("host") as batch:
        for name, _coltype in reversed(_HOST_COLUMNS):
            if name in host_columns:
                batch.drop_column(name)
