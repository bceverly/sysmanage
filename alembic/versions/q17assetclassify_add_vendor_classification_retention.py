# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""discovered_asset vendor + classification; policy retention_days (Phase 21.6 S5)

Tenant data. ``vendor`` is the IEEE-registered maker of the MAC (from the
table the server ships); ``device_type`` / ``classification`` are the
engine's labeled guess with its confidence and reasons; ``retention_days``
is how long a device may go unseen before it is forgotten (default 30).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q17assetclassify
Revises: q16netsweep
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q17assetclassify"
down_revision: Union[str, None] = "q16netsweep"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ASSET_COLUMNS = (
    ("vendor", lambda: sa.String(length=128)),
    ("device_type", lambda: sa.String(length=32)),
    ("classification", sa.JSON),
)


def _columns(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "discovered_asset" in tables:
        have = _columns(insp, "discovered_asset")
        for name, kind in _ASSET_COLUMNS:
            if name not in have:
                op.add_column(
                    "discovered_asset", sa.Column(name, kind(), nullable=True)
                )
    if "network_discovery_policy" in tables and "retention_days" not in _columns(
        insp, "network_discovery_policy"
    ):
        op.add_column(
            "network_discovery_policy",
            sa.Column(
                "retention_days", sa.Integer(), nullable=False, server_default="30"
            ),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "discovered_asset" in tables:
        have = _columns(insp, "discovered_asset")
        with op.batch_alter_table("discovered_asset") as batch:
            for name, _kind in _ASSET_COLUMNS:
                if name in have:
                    # expand-contract-ok: reverse of this revision's add_column.
                    batch.drop_column(name)
    if "network_discovery_policy" in tables and "retention_days" in _columns(
        insp, "network_discovery_policy"
    ):
        with op.batch_alter_table("network_discovery_policy") as batch:
            # expand-contract-ok: reverse of this revision's add_column.
            batch.drop_column("retention_days")
