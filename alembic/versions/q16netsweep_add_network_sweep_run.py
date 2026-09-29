# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add network_sweep_run and network_discovery_policy.sweep_enabled (Phase 21.6 S4)

Tenant data: every operator-requested active sweep (range, rate, who, which
agent, outcome), and a separate opt-in for sweeping at all -- listening is
quiet, a sweep puts traffic on the network.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q16netsweep
Revises: q15assetexcl
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q16netsweep"
down_revision: Union[str, None] = "q15assetexcl"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_RUNS = "network_sweep_run"
_POLICY = "network_discovery_policy"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if _POLICY in tables and "sweep_enabled" not in {
        c["name"] for c in insp.get_columns(_POLICY)
    }:
        op.add_column(
            _POLICY,
            sa.Column(
                "sweep_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if _RUNS in tables:
        return
    op.create_table(
        _RUNS,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("cidr", sa.String(length=64), nullable=False),
        sa.Column("rate", sa.Integer(), nullable=False),
        sa.Column("addresses", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column(
            "agent_host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("command_id", sa.String(length=36), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("probed", sa.Integer(), nullable=True),
        sa.Column("devices_found", sa.Integer(), nullable=True),
    )
    op.create_index("ix_network_sweep_run_cidr", _RUNS, ["cidr"])
    op.create_index("ix_network_sweep_run_status", _RUNS, ["status"])
    op.create_index("ix_network_sweep_run_agent_host_id", _RUNS, ["agent_host_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if _RUNS in tables:
        op.drop_table(_RUNS)
    if _POLICY in tables and "sweep_enabled" in {
        c["name"] for c in insp.get_columns(_POLICY)
    }:
        # expand-contract-ok: reverse of this revision's add_column.
        with op.batch_alter_table(_POLICY) as batch:
            batch.drop_column("sweep_enabled")
