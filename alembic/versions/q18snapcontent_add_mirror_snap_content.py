# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create mirror_snap_content (tenant partition) — Phase 17.1 (S3)

One row per (mirror, snap): the snap name + channel tracked for capture into a
mirror, plus capture bookkeeping (status / last message id / last capture time /
error).  The captured blobs + assertions live on disk under the mirror's
``snaps`` dir; these rows drive the ``snap_proxy_engine`` capture plan and let a
later content-view publish materialize the snaps into the version store.

Part of the TENANT chain (``mirror_repository`` / ``mirror_snapshot`` are
unprefixed tenant tables), chained off ``q17snapchan``.  Idempotent; safe on
SQLite + PostgreSQL.

Revision ID: q18snapcontent
Revises: q17snapchan
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "q18snapcontent"
down_revision: Union[str, None] = "q17snapchan"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "mirror_snap_content"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("repository_id", GUID(), nullable=False),
            sa.Column("snap_name", sa.String(length=100), nullable=False),
            sa.Column("channel", sa.String(length=100), nullable=False),
            sa.Column("confinement", sa.String(length=20), nullable=True),
            sa.Column("capture_status", sa.String(length=20), nullable=False),
            sa.Column("last_capture_message_id", sa.String(length=80), nullable=True),
            sa.Column("last_capture_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["repository_id"], ["mirror_repository.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint(
                "repository_id", "snap_name", name="uq_mirror_snap_content"
            ),
        )
        op.create_index("ix_%s_repository_id" % _TABLE, _TABLE, ["repository_id"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_index("ix_%s_repository_id" % _TABLE, table_name=_TABLE)
        op.drop_table(_TABLE)
