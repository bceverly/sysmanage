"""add cron_schedule column to airgap_collection_run (Phase 11.1 follow-up)

Revision ID: i7airgap60cron
Revises: h6airgap50delta
Create Date: 2026-05-11 09:00:00.000000

Adds ``airgap_collection_run.cron_schedule`` so a single run row can
carry its own cron expression and be re-fired by the server-side
scheduler tick (POST ``/airgap/collector/collection/runs/tick``) without
requiring a separate ``AirgapCollectionSchedule`` row.

This is the Phase 11.1 follow-up companion to ``cron_schedule`` support
added to ``airgap_collector_engine.build_collection_run_plan`` — see
ROADMAP.md §11.1 for the deferred-enhancement context.

SQLite-safe: uses ``op.batch_alter_table(recreate="auto")`` so the
upgrade path works on the SQLite test database as well as Postgres
production.  No FKs on this column (it's a plain VARCHAR).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "i7airgap60cron"
down_revision: Union[str, None] = "h6airgap50delta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("airgap_collection_run"):
        return
    cols = {c["name"] for c in insp.get_columns("airgap_collection_run")}
    if "cron_schedule" in cols:
        return
    with op.batch_alter_table("airgap_collection_run", recreate="auto") as batch:
        batch.add_column(
            sa.Column("cron_schedule", sa.String(length=200), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("airgap_collection_run"):
        return
    cols = {c["name"] for c in insp.get_columns("airgap_collection_run")}
    if "cron_schedule" not in cols:
        return
    with op.batch_alter_table("airgap_collection_run", recreate="auto") as batch:
        batch.drop_column("cron_schedule")
