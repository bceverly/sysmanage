# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add hardware tool install (Phase 23.1 S6)

``hardware_tool_install``: the last smartmontools install the server asked a
host for (by an operator, or automatically once an administrator turned that
on), and what the agent answered.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q43hwtools
Revises: q42hwhealth
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q43hwtools"
down_revision: Union[str, None] = "q42hwhealth"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "hardware_tool_install"
_INDEX = "ix_hardware_tool_install_command_id"


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "host" not in tables:
        return
    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("package", sa.String(64), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("command_id", sa.String(36), nullable=True),
            sa.Column("requested_by", sa.String(255), nullable=True),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        )
    if _INDEX not in {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["command_id"])


def downgrade() -> None:
    if _TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(_TABLE)
