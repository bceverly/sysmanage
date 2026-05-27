"""airgap_collection_target → mirror_repository / mirror_snapshot FKs (Phase 12 Option B).

Revision ID: x4airgap80optB
Revises: w3airgap70orch
Create Date: 2026-05-27 21:00:00.000000

Wires each AirgapCollectionTarget row to a specific mirror_repository
plus the snapshot of that mirror the run actually bundled.  This
collapses the two parallel apt-mirror / reposync pipelines (collector
vs. repository_mirroring) into one: the collector now reads from the
mirror's snapshot tree instead of running its own upstream fetch.

Columns added:

  mirror_id
      FK to mirror_repository.  Stamped at run creation when the
      operator picks a mirror.  Required for new runs; nullable on
      the schema for back-compat with any legacy rows.

  source_snapshot_id
      FK to mirror_snapshot.  Populated by the orchestrator when it
      advances QUEUED → MIRRORING — at that point all per-target
      snapshots have completed and we pin the snapshot the rsync
      plan will read from.  Nullable until that transition.

Idempotent: each column add is guarded by an ``inspect()`` check so
re-running on a partially-migrated DB is a no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID


revision: str = "x4airgap80optB"
down_revision: Union[str, None] = "w3airgap70orch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "airgap_collection_target"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        if "mirror_id" not in existing:
            batch.add_column(sa.Column("mirror_id", GUID(), nullable=True))
            batch.create_foreign_key(
                "fk_airgap_collection_target_mirror_id",
                "mirror_repository",
                ["mirror_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "source_snapshot_id" not in existing:
            batch.add_column(
                sa.Column("source_snapshot_id", GUID(), nullable=True)
            )
            batch.create_foreign_key(
                "fk_airgap_collection_target_source_snapshot_id",
                "mirror_snapshot",
                ["source_snapshot_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    with op.batch_alter_table(_TABLE, recreate="auto") as batch:
        if "source_snapshot_id" in existing:
            batch.drop_constraint(
                "fk_airgap_collection_target_source_snapshot_id",
                type_="foreignkey",
            )
            batch.drop_column("source_snapshot_id")
        if "mirror_id" in existing:
            batch.drop_constraint(
                "fk_airgap_collection_target_mirror_id",
                type_="foreignkey",
            )
            batch.drop_column("mirror_id")
