# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_run: when its decryption keys were released (2026-10-25)

Tenant data.  An encrypted repository's restore, listing or what-changed
needs the policy's secret key on the host for that one job (Pro+
backup_engine, 24.6 S4).  The agent fetches it over HTTPS for its own run
-- never through the message queue, so it is never written to the server's
database -- and ``key_released_at`` makes that a one-time release.
Additive, idempotent; safe on SQLite + PostgreSQL.

Revision ID: q64backupkeyrelease
Revises: q63backupencrypt
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q64backupkeyrelease"
down_revision: Union[str, None] = "q63backupencrypt"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _has(insp) -> bool:
    return "key_released_at" in {c["name"] for c in insp.get_columns("backup_run")}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_run" in set(insp.get_table_names()) and not _has(insp):
        op.add_column(
            "backup_run", sa.Column("key_released_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_run" in set(insp.get_table_names()) and _has(insp):
        with op.batch_alter_table("backup_run") as batch:
            batch.drop_column("key_released_at")
