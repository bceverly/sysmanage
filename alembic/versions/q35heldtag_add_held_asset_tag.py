# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add held_asset_tag (Phase 23.2 S5)

Asset tags waiting for a machine that has not reported in yet: a CSV import
row that matched no machine, or a tag given to a bare-metal box before it had
an OS.  Applied and deleted when the machine first appears.  In the tenant
database beside ``machine``.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q35heldtag
Revises: q34assettag
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q35heldtag"
down_revision: Union[str, None] = "q34assettag"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "held_asset_tag"
_INDEX = "ix_held_asset_tag_identifier"


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in set(inspect(bind).get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("identifier", sa.String(255), nullable=False),
            sa.Column("asset_tag", sa.String(128), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.String(255), nullable=True),
            sa.UniqueConstraint(
                "kind", "identifier", name="uq_held_asset_tag_identity"
            ),
            sa.UniqueConstraint("asset_tag", name="uq_held_asset_tag_tag"),
        )
    indexes = {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, ["identifier"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE in set(inspect(bind).get_table_names()):
        op.drop_table(_TABLE)
