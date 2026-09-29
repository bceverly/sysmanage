# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add discovered_asset_exclusion (Phase 21.6 S3)

Tenant data: the permanent "this device is known and fine" decisions. Audit
rows keyed by device identity (MAC), so they survive DHCP renumbering;
revoked rows are kept as history.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q15assetexcl
Revises: q14netdiscpolicy
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q15assetexcl"
down_revision: Union[str, None] = "q14netdiscpolicy"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "discovered_asset_exclusion"


def upgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("identity", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=1000), nullable=True),
    )
    op.create_index("ix_discovered_asset_exclusion_identity", _TABLE, ["identity"])
    op.create_index("ix_discovered_asset_exclusion_revoked_at", _TABLE, ["revoked_at"])


def downgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        op.drop_table(_TABLE)
