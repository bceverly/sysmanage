# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add clock_bound + 'Manage Time Sync' role (Phase 23.3 S3)

``clock_bound`` overrides the server-wide clock offset bounds for the tenant,
a site or a tag.  The role edits the bounds (and, from S5, the fleet NTP
policy).  Unlike q34, the role is granted in the SAME migration -- to every
administrator -- so an upgraded server is never left with a role nobody holds
(the q36 lesson).

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q38clockbound
Revises: q37clocksync
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q38clockbound"
down_revision: Union[str, None] = "q37clocksync"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "clock_bound"
_ROLE_NAME = "Manage Time Sync"
# The "Host" security role group (fixed id from the role seed migration).
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"

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
            sa.Column("scope_kind", sa.String(16), nullable=False),
            sa.Column("scope_ref", sa.String(64), nullable=False, server_default=""),
            sa.Column("warning_ms", sa.Float(), nullable=False),
            sa.Column("critical_ms", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.String(255), nullable=True),
            sa.UniqueConstraint("scope_kind", "scope_ref", name="uq_clock_bound_scope"),
        )
    _seed_role(bind)


def _seed_role(bind) -> None:
    tables = set(inspect(bind).get_table_names())
    if not {"security_roles", "user_security_roles", "user"} <= tables:
        return  # a tenant database: roles live with the registry
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    is_sqlite = bind.dialect.name == "sqlite"
    if not existing:
        # ``id``/``group_id`` are uuid columns on PostgreSQL, TEXT on SQLite.
        id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
        gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
        op.execute(
            sa.text(
                "INSERT INTO security_roles (id, name, description, group_id) "
                f"VALUES ({id_ph}, :name, :description, {gid_ph})"
            ).bindparams(
                id=str(uuid.uuid4()),
                name=_ROLE_NAME,
                description="Set clock offset bounds and the fleet time policy",
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
