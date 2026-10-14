# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add hardware health (Phase 23.1 S2)

``hardware_component`` (each host's drives, arrays, pools, sensors and memory
as last reported), ``hardware_event`` (one row per state change) and three
summary columns on ``host`` (worst state, when, and each source's status);
the "Manage Hardware Health" role (acknowledge / resolve events), granted to
administrators.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q42hwhealth
Revises: q41alertgroup
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q42hwhealth"
down_revision: Union[str, None] = "q41alertgroup"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ROLE_NAME = "Manage Hardware Health"
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
_HOST_COLUMNS = (
    ("hardware_state", sa.String(16)),
    ("hardware_reported_at", sa.DateTime()),
    ("hardware_sources", sa.Text()),
)
_INDEXES = (
    ("hardware_component", "ix_hardware_component_host_id", ["host_id"]),
    ("hardware_component", "ix_hardware_component_state", ["state"]),
    ("hardware_event", "ix_hardware_event_host_id", ["host_id"]),
    ("hardware_event", "ix_hardware_event_host_time", ["host_id", "occurred_at"]),
    ("hardware_event", "ix_hardware_event_open", ["acknowledged_at", "resolved_at"]),
)


def _host_fk():
    return sa.ForeignKey("host.id", ondelete="CASCADE")


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    _seed_role(bind, tables)
    if "host" not in tables:
        return
    if "hardware_component" not in tables:
        op.create_table(
            "hardware_component",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), _host_fk(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("ident", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("reasons", sa.Text(), nullable=True),
            sa.Column("metrics", sa.Text(), nullable=True),
            sa.Column("source", sa.String(64), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("state_since", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "host_id", "kind", "ident", name="uq_hardware_component"
            ),
        )
    if "hardware_event" not in tables:
        op.create_table(
            "hardware_event",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), _host_fk(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("ident", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("from_state", sa.String(16), nullable=True),
            sa.Column("to_state", sa.String(16), nullable=False),
            sa.Column("reasons", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("acknowledged_by", sa.String(255), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_by", sa.String(255), nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
        )
    for table, name, columns in _INDEXES:
        if name not in {ix["name"] for ix in inspect(bind).get_indexes(table)}:
            op.create_index(name, table, columns)
    existing = {c["name"] for c in inspect(bind).get_columns("host")}
    for name, column_type in _HOST_COLUMNS:
        if name not in existing:
            op.add_column("host", sa.Column(name, column_type, nullable=True))


def _seed_role(bind, tables) -> None:
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
                description="Acknowledge and resolve hardware health events",
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
    for table in ("hardware_event", "hardware_component"):
        if table in tables:
            op.drop_table(table)
    if "host" not in tables:
        return
    existing = {c["name"] for c in inspect(bind).get_columns("host")}
    drop = [name for name, _ in _HOST_COLUMNS if name in existing]
    if drop:
        with op.batch_alter_table("host") as batch:
            for name in drop:
                batch.drop_column(name)
