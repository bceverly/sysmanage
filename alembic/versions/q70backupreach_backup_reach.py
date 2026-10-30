# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_reach: can each host reach the backup storage? (2026-10-30)

Tenant data.  The agent's last TCP check of the storage host's NFS port at
the address the host would mount its repository from; a host that cannot
reach it is not offered backups (production: the server's own droplet
cannot reach the home NAS).  One row per host, removed with it (ON DELETE
CASCADE, as backup_equip's).  Additive, idempotent; safe on SQLite +
PostgreSQL.

Revision ID: q70backupreach
Revises: q69backupverify
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q70backupreach"
down_revision: Union[str, None] = "q69backupverify"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLE = "backup_reach"


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
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("reachable", sa.Boolean(), nullable=True),
        sa.Column("error", sa.String(255), nullable=True),
        sa.Column("command_id", sa.String(36), nullable=True, index=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    if TABLE in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
