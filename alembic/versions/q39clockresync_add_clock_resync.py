# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add clock_resync + 'Resync Host Clock' role (Phase 23.3 S5)

``clock_resync`` holds each spot resynchronization of a host's clock, released
in waves.  The role is seeded AND granted to every administrator in the same
step, so an upgraded server is never left with a role nobody holds.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q39clockresync
Revises: q38clockbound
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q39clockresync"
down_revision: Union[str, None] = "q38clockbound"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "clock_resync"
_ROLE_NAME = "Resync Host Clock"
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"
_INDEXES = (
    ("ix_clock_resync_status", ["status", "requested_at"]),
    ("ix_clock_resync_host_id", ["host_id"]),
    ("ix_clock_resync_batch_id", ["batch_id"]),
    ("ix_clock_resync_command_id", ["command_id"]),
)

_GRANT_SELECT = """
    FROM "user" u
    JOIN security_roles target ON target.name = :role
    WHERE u.is_admin = :yes AND NOT EXISTS (
        SELECT 1 FROM user_security_roles ex
        WHERE ex.user_id = u.id AND ex.role_id = target.id
    )
"""
_GRANT_PG = (
    "INSERT INTO user_security_roles (id, user_id, role_id, granted_at) "
    "SELECT gen_random_uuid(), u.id, target.id, now()" + _GRANT_SELECT
)
_GRANT_SQLITE = (
    "INSERT INTO user_security_roles (id, user_id, role_id, granted_at) "
    "SELECT lower("
    "substr(hex(randomblob(4)),1,8)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(2)),1,4)||'-'||"
    "substr(hex(randomblob(6)),1,12)), u.id, target.id, datetime('now')" + _GRANT_SELECT
)


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(inspect(bind).get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("batch_id", GUID(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("requested_by", sa.String(255), nullable=True),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("command_id", sa.String(36), nullable=True),
            sa.Column("offset_before_ms", sa.Float(), nullable=True),
            sa.Column("reported_after_ms", sa.Float(), nullable=True),
            sa.Column("service", sa.String(16), nullable=True),
            sa.Column("method", sa.String(64), nullable=True),
            sa.Column("error", sa.String(32), nullable=True),
            sa.Column("detail", sa.String(500), nullable=True),
        )
    existing = {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, columns)
    _seed_role(bind)


def _seed_role(bind) -> None:
    tables = set(inspect(bind).get_table_names())
    if not {"security_roles", "user_security_roles", "user"} <= tables:
        return  # a tenant database: roles live with the registry
    is_sqlite = bind.dialect.name == "sqlite"
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    if not existing:
        id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
        gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
        op.execute(
            sa.text(
                "INSERT INTO security_roles (id, name, description, group_id) "
                f"VALUES ({id_ph}, :name, :description, {gid_ph})"
            ).bindparams(
                id=str(uuid.uuid4()),
                name=_ROLE_NAME,
                description="Step a host's clock through its time service",
                group_id=_HOST_GROUP_ID,
            )
        )
    sql = _GRANT_SQLITE if is_sqlite else _GRANT_PG
    op.execute(sa.text(sql).bindparams(role=_ROLE_NAME, yes=True))


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if {"security_roles", "user_security_roles"} <= tables:
        op.execute(
            sa.text(
                "DELETE FROM user_security_roles WHERE role_id IN "
                "(SELECT id FROM security_roles WHERE name = :name)"
            ).bindparams(name=_ROLE_NAME)
        )
        op.execute(
            sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                name=_ROLE_NAME
            )
        )
    if _TABLE in tables:
        op.drop_table(_TABLE)
