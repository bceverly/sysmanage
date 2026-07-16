# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add air-gap collection schedule table (Phase 11.x B2)

Revision ID: g5airgap40schedule
Revises: f4airgap30install
Create Date: 2026-05-10 09:30:00.000000

One new table backing cron-driven recurring collection runs:

  airgap_collection_schedule  — name, cron, enabled, frozen target
                                request body, last_run / next_run

Cron parsing on the tick path goes through ``automation_engine.
next_run_from_cron`` (both engines are Enterprise tier; a deployment
that licenses one almost always licenses the other).  The OSS route
returns 503 with a clear "schedule will not auto-fire" message if
``automation_engine`` isn't loaded; the schedule rows still validate
+ persist so the operator can fix the license and resume scheduled
operation without losing the schedule definitions.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "g5airgap40schedule"
down_revision: Union[str, None] = "f4airgap30install"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("airgap_collection_schedule"):
        op.create_table(
            "airgap_collection_schedule",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column(
                "cron",
                sa.String(length=200),
                nullable=False,
                server_default="0 3 * * *",
            ),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("target_request_json", sa.Text(), nullable=False),
            sa.Column("last_run", sa.DateTime(), nullable=True),
            sa.Column("last_status", sa.String(length=40), nullable=True),
            sa.Column(
                "last_run_id",
                GUID(),
                sa.ForeignKey(
                    "airgap_collection_run.id",
                    name="fk_airgap_collection_schedule_last_run_id",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("next_run", sa.DateTime(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "name", name="uq_airgap_collection_schedule_name"
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("airgap_collection_schedule"):
        op.drop_table("airgap_collection_schedule")
