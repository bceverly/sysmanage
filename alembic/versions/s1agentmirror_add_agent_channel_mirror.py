# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add airgap_agent_channel_mirror — Phase 12 private agent-install mirrors

Per-channel substitution of a private mirror for the upstream agent-install
channels (PPA / COPR / OBS / apk / pkg / winget / brew).  Phase 11.1 already
mirrors OS packages and repoints hosts that are already managed; this is the
bootstrap end, so a host provisioned in an air-gapped site can install the
agent itself and enroll.

Keyed by channel, not distro: one ``copr`` row covers the whole RHEL family.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s1agentmirror
Revises: r7discovery
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "s1agentmirror"
down_revision: Union[str, None] = "r7discovery"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "airgap_agent_channel_mirror"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("mirror_url", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", name="uq_airgap_agent_channel_mirror_channel"),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
