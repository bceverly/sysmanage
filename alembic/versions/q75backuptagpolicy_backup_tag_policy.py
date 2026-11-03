# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup policies by tag (Pro+ backup_engine, ROADMAP 24.6, 2026-11-03)

Tenant data.  ``backup_tag_policy`` is a template: every host carrying its
tag gets its settings (JSON, the per-host policy's own fields) on its own
``backup_policy`` row, which the scheduler already runs.  A host covered by
several resolves to the lowest ``priority``; a host's own policy (set with
Configure) always beats them.  ``backup_policy.tag_policy_id`` names the tag
policy a host's settings came from (NULL = the host's own policy).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q75backuptagpolicy
Revises: q74backupdrift
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q75backuptagpolicy"
down_revision: Union[str, None] = "q74backupdrift"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

TABLE = "backup_tag_policy"


def _tables(insp):
    return set(insp.get_table_names())


def _create_table(insp) -> None:
    if TABLE in _tables(insp) or "tags" not in _tables(insp):
        return
    op.create_table(
        TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "tag_id",
            GUID(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("settings", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name", name="uq_backup_tag_policy_name"),
    )


def _add_policy_column(insp) -> None:
    if "backup_policy" not in _tables(insp):
        return
    present = {c["name"] for c in insp.get_columns("backup_policy")}
    if "tag_policy_id" not in present:
        # No foreign key on purpose: SQLite cannot add one to an existing
        # table, and the service clears the reference when a tag policy goes.
        op.add_column(
            "backup_policy", sa.Column("tag_policy_id", GUID(), nullable=True)
        )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    _create_table(insp)
    _add_policy_column(insp)


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if "backup_policy" in _tables(insp):
        present = {c["name"] for c in insp.get_columns("backup_policy")}
        if "tag_policy_id" in present:
            with op.batch_alter_table("backup_policy") as batch:
                batch.drop_column("tag_policy_id")
    if TABLE in _tables(insp):
        op.drop_table(TABLE)
