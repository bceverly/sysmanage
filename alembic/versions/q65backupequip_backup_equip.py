# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_equip: the last "Equip for backup" of each host (2026-10-27)

Tenant data.  "Equip for backup" has the host's agent install restate (Ubuntu's
PPA, FreeBSD's release package); this keeps the latest attempt per host -- its
status, the agent's reason code and output on failure, what it installed --
so the Backups page can say "Equipping" and, when it failed, why.  The row
goes with its host (ON DELETE CASCADE, as backup_policy's does).  Additive,
idempotent; safe on SQLite + PostgreSQL.

Revision ID: q65backupequip
Revises: q64backupkeyrelease
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q65backupequip"
down_revision: Union[str, None] = "q64backupkeyrelease"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLE = "backup_equip"


def upgrade() -> None:
    if TABLE in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("installed", sa.String(32), nullable=True),
        sa.Column("command_id", sa.String(36), nullable=True, index=True),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    if TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
