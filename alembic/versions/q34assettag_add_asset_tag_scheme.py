# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add asset_tag_scheme + 'Manage Asset Tags' role (Phase 23.2 S3)

The tenant's asset-tag naming scheme (one row, in the tenant database beside
the machines it governs) and the role that edits it and sets machine tags.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q34assettag
Revises: q33machine
"""

import uuid
from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q34assettag"
down_revision: Union[str, None] = "q33machine"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "asset_tag_scheme"
_ROLE_NAME = "Manage Asset Tags"
_HOST_GROUP_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(inspect(bind).get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("mode", sa.String(16), nullable=False, server_default="builder"),
            sa.Column("prefix", sa.String(32), nullable=False, server_default=""),
            sa.Column("separator", sa.String(1), nullable=False, server_default="-"),
            sa.Column("digits", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("suffix", sa.String(32), nullable=False, server_default=""),
            sa.Column("pattern", sa.String(256), nullable=False, server_default=""),
            sa.Column(
                "enforce", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("updated_by", sa.String(255), nullable=True),
        )
    _seed_role(bind)


def _seed_role(bind) -> None:
    """Idempotently seed the role in the Host group (where the role table is)."""
    if "security_roles" not in inspect(bind).get_table_names():
        return  # a tenant database: roles live with the registry
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
            description="Set machine asset tags and the naming scheme",
            group_id=_HOST_GROUP_ID,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "security_roles" in inspect(bind).get_table_names():
        op.execute(
            sa.text("DELETE FROM security_roles WHERE name = :name").bindparams(
                name=_ROLE_NAME
            )
        )
    if _TABLE in set(inspect(bind).get_table_names()):
        op.drop_table(_TABLE)
