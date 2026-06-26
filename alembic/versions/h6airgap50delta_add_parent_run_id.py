"""add parent_run_id for delta collection (Phase 11 B3)

Revision ID: h6airgap50delta
Revises: g5airgap40schedule
Create Date: 2026-05-10 10:00:00.000000

Adds ``airgap_collection_run.parent_run_id`` so a delta run can link
back to the snapshot it builds on.  NULL = full snapshot.

SQLite-safe: uses ``op.batch_alter_table(recreate="auto")`` with an
explicit FK name (named constraints are required for batch mode —
see Phase 10.5 footgun in the y6idp10extauth migration).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "h6airgap50delta"
down_revision: Union[str, None] = "g5airgap40schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("airgap_collection_run"):
        return
    cols = {c["name"] for c in insp.get_columns("airgap_collection_run")}
    if "parent_run_id" in cols:
        return
    with op.batch_alter_table("airgap_collection_run", recreate="auto") as batch:
        batch.add_column(
            sa.Column(
                "parent_run_id",
                GUID(),
                sa.ForeignKey(
                    "airgap_collection_run.id",
                    name="fk_airgap_collection_run_parent_run_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("airgap_collection_run"):
        return
    cols = {c["name"] for c in insp.get_columns("airgap_collection_run")}
    if "parent_run_id" not in cols:
        return
    with op.batch_alter_table("airgap_collection_run", recreate="auto") as batch:
        batch.drop_column("parent_run_id")
