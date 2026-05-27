"""airgap_collection_run.worker_message_id + burn_device (Phase 12 — orchestrator).

Revision ID: w3airgap70orch
Revises: v2mirror70peraction
Create Date: 2026-05-27 20:00:00.000000

Adds two columns to ``airgap_collection_run``:

  worker_message_id
      Tracks which agent command is currently driving the run.
      Stamped by ``airgap_run_tick`` at dispatch, cleared by the
      result handler.  The orchestrator skips rows whose
      ``worker_message_id`` is non-NULL on its next tick so a slow-
      running plan isn't double-dispatched.

  burn_device
      Optional optical-burn target.  When set, the orchestrator
      advances ISO_BUILT → BURNING by dispatching the engine's
      ``build_burn_plan``.  When NULL, the run goes ISO_BUILT →
      COMPLETE directly (the "build an ISO file and download" path).

Idempotent: each column add is guarded by an ``inspect()`` check so
re-running on a partially-migrated DB is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "w3airgap70orch"
down_revision: Union[str, None] = "v2mirror70peraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "airgap_collection_run"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        if "worker_message_id" not in existing:
            batch.add_column(
                sa.Column("worker_message_id", sa.String(length=80), nullable=True)
            )
        if "burn_device" not in existing:
            batch.add_column(
                sa.Column("burn_device", sa.String(length=200), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        if "burn_device" in existing:
            batch.drop_column("burn_device")
        if "worker_message_id" in existing:
            batch.drop_column("worker_message_id")
