# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add provisioning_readiness (PXE preflight cache) — Phase 18.2 S1

One row per host caching the most recent PXE-readiness probe: which
DHCP/TFTP/HTTP/boot-loader tools are present, what is already listening on
the DHCP/TFTP ports (which decides own-DHCP vs proxyDHCP), and the
in-flight/last-result markers for the probe, the tool install, and the
config-advisor apply.

Mirrors ``mirror_setup_status`` (Phase 10.4.1) in shape and lifecycle.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r5provreadiness
Revises: r4compresconfig
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "r5provreadiness"
down_revision: Union[str, None] = "r4compresconfig"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "provisioning_readiness"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    # No FK to host when the host table is absent (fresh partition DBs are
    # built chain-by-chain); the column still carries the id.
    host_fk = (
        [sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE")]
        if insp.has_table("host")
        else []
    )
    op.create_table(
        _TABLE,
        sa.Column("host_id", GUID(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=True),
        sa.Column("distro", sa.String(length=40), nullable=True),
        sa.Column("firewall_flavor", sa.String(length=20), nullable=True),
        sa.Column("dhcp_mode", sa.String(length=10), nullable=True),
        sa.Column("last_check_at", sa.DateTime(), nullable=True),
        sa.Column("last_check_message_id", sa.String(length=36), nullable=True),
        sa.Column("last_check_error", sa.Text(), nullable=True),
        sa.Column("install_status", sa.String(length=20), nullable=False),
        sa.Column("last_install_at", sa.DateTime(), nullable=True),
        sa.Column("last_install_message_id", sa.String(length=36), nullable=True),
        sa.Column("last_install_error", sa.Text(), nullable=True),
        sa.Column("apply_status", sa.String(length=20), nullable=False),
        sa.Column("last_apply_at", sa.DateTime(), nullable=True),
        sa.Column("last_apply_message_id", sa.String(length=36), nullable=True),
        sa.Column("last_apply_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("host_id"),
        *host_fk,
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
