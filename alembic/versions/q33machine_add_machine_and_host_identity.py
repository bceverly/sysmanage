# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add machine + host hardware identity (Phase 23.2 S2)

``machine`` is the hardware a host runs on; the asset tag lives there, so it
survives an OS reinstall and is shared by every OS on a multi-boot machine.
``host`` gains a soft reference to it, the identity it reported, and a
pending-conflict pair for links an admin must confirm.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q33machine
Revises: q32ssostate
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q33machine"
down_revision: Union[str, None] = "q32ssostate"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "machine"

_HOST_COLUMNS = (
    ("machine_id", GUID()),
    ("hw_match_key", sa.String(36)),
    ("hw_system_uuid", sa.String(36)),
    ("hw_system_serial", sa.String(255)),
    ("hw_board_serial", sa.String(255)),
    ("hw_identity_status", sa.Text()),
    ("hw_identity_updated_at", sa.DateTime()),
    ("machine_conflict_id", GUID()),
    ("machine_conflict_reason", sa.String(32)),
)
_HOST_INDEXES = (
    ("ix_host_machine_id", "machine_id"),
    ("ix_host_hw_match_key", "hw_match_key"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(inspect(bind).get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("match_key", sa.String(36), nullable=False),
            sa.Column("system_uuid", sa.String(36), nullable=True),
            sa.Column("system_serial", sa.String(255), nullable=True),
            sa.Column("board_serial", sa.String(255), nullable=True),
            sa.Column("vendor", sa.String(255), nullable=True),
            sa.Column("model", sa.String(255), nullable=True),
            sa.Column(
                "is_virtual", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column("asset_tag", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("asset_tag", name="uq_machine_asset_tag"),
        )
    machine_indexes = {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}
    if "ix_machine_match_key" not in machine_indexes:
        op.create_index("ix_machine_match_key", _TABLE, ["match_key"])

    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    for name, coltype in _HOST_COLUMNS:
        if name not in host_columns:
            op.add_column("host", sa.Column(name, coltype, nullable=True))
    host_indexes = {ix["name"] for ix in inspect(bind).get_indexes("host")}
    for index_name, column in _HOST_INDEXES:
        if index_name not in host_indexes:
            op.create_index(index_name, "host", [column])


def downgrade() -> None:
    bind = op.get_bind()
    host_indexes = {ix["name"] for ix in inspect(bind).get_indexes("host")}
    for index_name, _column in _HOST_INDEXES:
        if index_name in host_indexes:
            op.drop_index(index_name, table_name="host")
    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    with op.batch_alter_table("host") as batch:
        for name, _coltype in reversed(_HOST_COLUMNS):
            if name in host_columns:
                batch.drop_column(name)
    if _TABLE in set(inspect(bind).get_table_names()):
        op.drop_table(_TABLE)
