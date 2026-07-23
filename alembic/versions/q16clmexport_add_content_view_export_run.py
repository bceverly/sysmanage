# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create content-view air-gap export runs (tenant partition) — Phase 16 (S7a)

One row per "export a published content-view version to signed air-gap media"
job.  Per-tenant operation over a SHARED content-view version, so it lives in the
TENANT chain (unprefixed); all references to the shared catalog IDs (content
view / version) are SOFT -- NO ForeignKey (cross-partition).

Part of the TENANT chain, chained off ``q15clmbind`` (the content-lifecycle
promotion-state migration).  Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q16clmexport
Revises: q15clmbind
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "q16clmexport"
down_revision: Union[str, None] = "q15clmbind"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_EXPORT = "content_view_export_run"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_EXPORT):
        op.create_table(
            _EXPORT,
            sa.Column("id", GUID(), primary_key=True),
            # SOFT cross-partition refs to shared catalog IDs — no FK.
            sa.Column("content_view_id", GUID(), nullable=False),
            sa.Column("content_view_version_id", GUID(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("iso_label", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("worker_message_id", sa.String(length=80), nullable=True),
            sa.Column("iso_path", sa.String(length=500), nullable=True),
            sa.Column("iso_sha256", sa.String(length=64), nullable=True),
            sa.Column("media_size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", GUID(), nullable=True),  # soft ref to user
        )
        op.create_index("ix_%s_content_view_id" % _EXPORT, _EXPORT, ["content_view_id"])
        op.create_index("ix_%s_status" % _EXPORT, _EXPORT, ["status"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_EXPORT):
        op.drop_table(_EXPORT)
