# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add discovered_asset, discovered_asset_sighting, network_discovery_observer (Phase 21.6 S1)

Tenant data: the devices agents see on their own segments, which agent saw
each one, and what each agent can and cannot see (its blind spots).

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q13assetdisc
Revises: q12builtinmetric
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q13assetdisc"
down_revision: Union[str, None] = "q12builtinmetric"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _discovered_asset():
    op.create_table(
        "discovered_asset",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("identity", sa.String(length=64), nullable=False),
        sa.Column("identity_kind", sa.String(length=8), nullable=False),
        sa.Column("mac", sa.String(length=17), nullable=True),
        sa.Column("mac_locally_administered", sa.Boolean(), nullable=False),
        sa.Column("last_ip", sa.String(length=45), nullable=True),
        sa.Column("ips", sa.JSON(), nullable=True),
        sa.Column("hostnames", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("methods", sa.JSON(), nullable=True),
        sa.Column(
            "managed_host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("managed_reason", sa.String(length=32), nullable=True),
        sa.Column("correlated_at", sa.DateTime(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_discovered_asset_identity", "discovered_asset", ["identity"], unique=True
    )
    op.create_index("ix_discovered_asset_mac", "discovered_asset", ["mac"])
    op.create_index(
        "ix_discovered_asset_managed_host_id", "discovered_asset", ["managed_host_id"]
    )
    op.create_index(
        "ix_discovered_asset_last_seen_at", "discovered_asset", ["last_seen_at"]
    )


def _discovered_asset_sighting():
    op.create_table(
        "discovered_asset_sighting",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "asset_id",
            GUID(),
            sa.ForeignKey("discovered_asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "observer_host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interface", sa.String(length=64), nullable=True),
        sa.Column("network", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("methods", sa.JSON(), nullable=True),
        sa.Column("sightings", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "asset_id", "observer_host_id", name="uq_discovered_asset_sighting"
        ),
    )
    op.create_index(
        "ix_discovered_asset_sighting_asset_id",
        "discovered_asset_sighting",
        ["asset_id"],
    )
    op.create_index(
        "ix_discovered_asset_sighting_observer_host_id",
        "discovered_asset_sighting",
        ["observer_host_id"],
    )


def _network_discovery_observer():
    op.create_table(
        "network_discovery_observer",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("networks", sa.JSON(), nullable=True),
        sa.Column("methods", sa.JSON(), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=True),
        sa.Column("reports", sa.Integer(), nullable=False),
        sa.Column("last_report_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_network_discovery_observer_host_id",
        "network_discovery_observer",
        ["host_id"],
        unique=True,
    )


_TABLES = {
    "discovered_asset": _discovered_asset,
    "discovered_asset_sighting": _discovered_asset_sighting,
    "network_discovery_observer": _network_discovery_observer,
}


def upgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table, create in _TABLES.items():
        if table not in existing:
            create()


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    for table in reversed(list(_TABLES)):
        if table in existing:
            op.drop_table(table)
