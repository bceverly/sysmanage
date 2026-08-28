# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add config_drift_finding for Phase 20.2 drift analysis.

One row per divergence between a host and a profile, carrying only its
LIFESPAN -- first seen, last seen, resolved. The run rows remain the record of
what happened; this exists because a run cannot answer "since when", which is
the column that makes a drift dashboard worth reading.

Revision ID: c22cfgdrift01
Revises: c21cfgprof01
"""

import sqlalchemy as sa
from alembic import op

from backend.persistence.models.core import GUID

revision = "c22cfgdrift01"
down_revision = "c21cfgprof01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the drift finding table."""
    op.create_table(
        "config_drift_finding",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "host_id",
            GUID(),
            sa.ForeignKey("host.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SET NULL, not CASCADE: deleting a profile must not silently erase the
        # record that hosts had drifted from it, for the same reason
        # config_profile_run.profile_id is softened.
        sa.Column(
            "profile_id",
            GUID(),
            sa.ForeignKey("config_profile.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("profile_name", sa.String(255), nullable=True),
        sa.Column("task_name", sa.String(500), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_id", GUID(), nullable=True),
        # The identity of a finding, enforced. Two ticks racing would otherwise
        # open two rows for one divergence and the age shown would depend on
        # which row the page happened to read.
        #
        # Declared INLINE rather than via create_unique_constraint: that is an
        # ALTER, which SQLite cannot do, and the tenant chain is exercised on
        # SQLite by tests/test_alembic_prefix_guard.py. c21cfgprof01 shipped
        # with exactly that mistake and only CI caught it.
        sa.UniqueConstraint(
            "host_id",
            "profile_id",
            "task_name",
            name="uq_config_drift_finding_identity",
        ),
    )
    op.create_index(
        "ix_config_drift_finding_open",
        "config_drift_finding",
        ["resolved_at", "last_seen_at"],
    )
    op.create_index(
        "ix_config_drift_finding_host",
        "config_drift_finding",
        ["host_id", "resolved_at"],
    )
    op.create_index(
        "ix_config_drift_finding_profile_id",
        "config_drift_finding",
        ["profile_id"],
    )


def downgrade() -> None:
    """Drop the drift finding table."""
    op.drop_index("ix_config_drift_finding_profile_id", "config_drift_finding")
    op.drop_index("ix_config_drift_finding_host", "config_drift_finding")
    op.drop_index("ix_config_drift_finding_open", "config_drift_finding")
    # No drop_constraint: the constraint is part of the table definition, and
    # dropping the table takes it with it.
    op.drop_table("config_drift_finding")
