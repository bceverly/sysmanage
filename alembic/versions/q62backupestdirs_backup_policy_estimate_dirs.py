# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup_policy: the first-backup estimate's largest directories (2026-10-25)

Tenant data.  Before a host's first scheduled backup the scheduler runs
restate's ``estimate`` and holds the backup when it would not fit the
target's free space (ROADMAP 24.8).  ``estimate_dirs`` (JSON
``[{path, bytes}]``, the ten largest) is where the card suggests leaving
things out.  Additive, idempotent; safe on SQLite + PostgreSQL.

Revision ID: q62backupestdirs
Revises: q61backupcachefix
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q62backupestdirs"
down_revision: Union[str, None] = "q61backupcachefix"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    if "estimate_dirs" not in {c["name"] for c in insp.get_columns("backup_policy")}:
        op.add_column(
            "backup_policy", sa.Column("estimate_dirs", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" not in set(insp.get_table_names()):
        return
    if "estimate_dirs" in {c["name"] for c in insp.get_columns("backup_policy")}:
        with op.batch_alter_table("backup_policy") as batch:
            batch.drop_column("estimate_dirs")
