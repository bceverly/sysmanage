# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add network_discovery_policy, network_discovery_dispatch; seed 'Manage Network Discovery' (Phase 21.6 S2)

Tenant data: whether this tenant's agents listen to their networks and how
often they report (absent = OFF), and what each host was last told so the
reconciler only sends a change. Seeds the ``Manage Network Discovery`` role
in the Host group: turning on network listening is a deliberate, separately
grantable decision.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q14netdiscpolicy
Revises: q13assetdisc
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q14netdiscpolicy"
down_revision: Union[str, None] = "q13assetdisc"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ROLE_NAME = "Manage Network Discovery"
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"


def _policy():
    op.create_table(
        "network_discovery_policy",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("report_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _dispatch():
    op.create_table(
        "network_discovery_dispatch",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("report_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("command_id", sa.String(length=36), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_network_discovery_dispatch_host_id",
        "network_discovery_dispatch",
        ["host_id"],
        unique=True,
    )


_TABLES = {
    "network_discovery_policy": _policy,
    "network_discovery_dispatch": _dispatch,
}


def _seed_role(bind) -> None:
    """Idempotently seed the 'Manage Network Discovery' role (Host group)."""
    if "security_roles" not in inspect(bind).get_table_names():
        return
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = :name"),
        {"name": _ROLE_NAME},
    ).scalar()
    if existing:
        return
    # ``id``/``group_id`` are uuid columns on PostgreSQL, plain TEXT on SQLite.
    is_sqlite = bind.dialect.name == "sqlite"
    id_ph = ":id" if is_sqlite else "CAST(:id AS uuid)"
    gid_ph = ":group_id" if is_sqlite else "CAST(:group_id AS uuid)"
    op.execute(
        sa.text(
            "INSERT INTO security_roles (id, name, description, group_id) "
            f"VALUES ({id_ph}, :name, :description, {gid_ph})"
        ).bindparams(
            id=str(uuid.uuid4()),
            name=_ROLE_NAME,
            description="Turn agent network discovery on or off and set how often agents report",
            group_id=_HOST_GROUP_ID,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table, create in _TABLES.items():
        if table not in existing:
            create()
    _seed_role(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "security_roles" in insp.get_table_names():
        op.execute(
            sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                name=_ROLE_NAME
            )
        )
    existing = set(insp.get_table_names())
    for table in reversed(list(_TABLES)):
        if table in existing:
            op.drop_table(table)
