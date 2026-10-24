# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backup: make sure cache_budget_gb and host_abilities exist (2026-10-23)

Tenant data.  ``backup_target.cache_budget_gb`` and
``backup_policy.host_abilities`` were added to q60sealkeep after a database
had already applied an earlier q60sealkeep, so on that database they never
appeared and the Backups page failed with "column
backup_target.cache_budget_gb does not exist".  This adds whichever of the
two is missing, and bumps every policy's ``config_version`` so each host
re-reports what its restate can do.

The columns belong to q60sealkeep; the downgrade leaves them for it.
Additive, idempotent; safe on SQLite + PostgreSQL.

Revision ID: q61backupcachefix
Revises: q60sealkeep
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q61backupcachefix"
down_revision: Union[str, None] = "q60sealkeep"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _columns(insp, table: str) -> set:
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "backup_target" in tables and "cache_budget_gb" not in _columns(
        insp, "backup_target"
    ):
        op.add_column(
            "backup_target", sa.Column("cache_budget_gb", sa.Integer(), nullable=True)
        )
    if "backup_policy" not in tables:
        return
    if "host_abilities" not in _columns(insp, "backup_policy"):
        op.add_column(
            "backup_policy", sa.Column("host_abilities", sa.Text(), nullable=True)
        )
    op.execute(sa.text("UPDATE backup_policy SET config_version = config_version + 1"))


def downgrade() -> None:
    """The columns are q60sealkeep's; its downgrade removes them."""
