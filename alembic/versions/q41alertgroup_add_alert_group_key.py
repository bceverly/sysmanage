# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add alert.group_key (Phase 23.3 S6)

Alerts notified together as one site digest share a key, so the digest can be
found, extended and resolved as one.  Nullable: an alert notified alone has
none.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q41alertgroup
Revises: q40ntppolicy
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q41alertgroup"
down_revision: Union[str, None] = "q40ntppolicy"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_INDEX = "ix_alert_group_key"


def upgrade() -> None:
    bind = op.get_bind()
    if "alert" not in set(inspect(bind).get_table_names()):
        return
    if "group_key" not in {c["name"] for c in inspect(bind).get_columns("alert")}:
        op.add_column("alert", sa.Column("group_key", sa.String(128), nullable=True))
    if _INDEX not in {ix["name"] for ix in inspect(bind).get_indexes("alert")}:
        op.create_index(_INDEX, "alert", ["group_key"])


def downgrade() -> None:
    bind = op.get_bind()
    if "alert" not in set(inspect(bind).get_table_names()):
        return
    if _INDEX in {ix["name"] for ix in inspect(bind).get_indexes("alert")}:
        op.drop_index(_INDEX, table_name="alert")
    if "group_key" in {c["name"] for c in inspect(bind).get_columns("alert")}:
        with op.batch_alter_table("alert") as batch:
            batch.drop_column("group_key")
