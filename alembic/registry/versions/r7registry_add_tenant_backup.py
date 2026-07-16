# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add_tenant_backup

Phase 13.1.F (per-tenant backup/RPO orchestration): records every per-tenant
backup attempt and every restore-verification so the control plane can report
RPO compliance and prove restorability.  SysManage orchestrates the schedule and
runs an operator-configured external backup command (orchestrate-only); it does
not store the backup bytes — ``artifact_ref`` is the opaque handle that command
reports.  Only this run-history table is OSS; the orchestration logic lives in
the licensed ``multitenancy_engine``.

Seventh migration in the **registry** chain (chains off ``r6registry``).
Idempotent and identical on SQLite (test) + PostgreSQL (prod).

Revision ID: r7registry
Revises: r6registry
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision: str = "r7registry"
down_revision: Union[str, None] = "r6registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "registry_tenant_backup"


def upgrade() -> None:
    """Create ``registry_tenant_backup`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    # The registry partition must exist for this table to make sense; skip on a
    # shared/tenant-only run (mirrors the rest of the registry chain).
    if "registry_tenant" not in existing:
        return
    if _TABLE in existing:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("tenant_id", GUID(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="backup"),
        sa.Column("verify_kind", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("rpo_seconds", sa.Integer(), nullable=True),
        sa.Column("artifact_ref", sa.String(1024), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["registry_tenant.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_registry_tenant_backup_tenant", _TABLE, ["tenant_id"])
    op.create_index(
        "ix_registry_tenant_backup_tenant_started",
        _TABLE,
        ["tenant_id", "started_at"],
    )


def downgrade() -> None:
    """Drop ``registry_tenant_backup`` (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in set(inspector.get_table_names()):
        return
    for index in (
        "ix_registry_tenant_backup_tenant_started",
        "ix_registry_tenant_backup_tenant",
    ):
        try:
            op.drop_index(index, table_name=_TABLE)
        except Exception:  # noqa: BLE001 — index may not exist; drop is best-effort
            pass
    op.drop_table(_TABLE)
