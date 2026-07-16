# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add air-gap repository tables (Phase 11.2)

Revision ID: e3airgap20repo
Revises: d2airgap10collect
Create Date: 2026-05-10 08:30:00.000000

Two new tables backing the Pro+ ``airgap_repository_engine``:

  airgap_ingestion_run        — one row per private-side ISO ingestion
  airgap_local_repository     — locally-served mirror, keyed (distro, version)

No cross-database FK to the collector tables — the two air-gap halves
never share a database.  The ingestion run records the manifest's
``signer_fingerprint`` + ``collector_iso_label`` so audit can correlate
across the gap by inspecting both halves' DBs after the fact.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "e3airgap20repo"
down_revision: Union[str, None] = "d2airgap10collect"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("airgap_ingestion_run"):
        op.create_table(
            "airgap_ingestion_run",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column("iso_path", sa.String(length=500), nullable=False),
            sa.Column("iso_sha256", sa.String(length=64), nullable=True),
            sa.Column("signer_fingerprint", sa.String(length=128), nullable=True),
            sa.Column("manifest_format_version", sa.Integer(), nullable=True),
            sa.Column("collector_iso_label", sa.String(length=80), nullable=True),
            sa.Column("captured_at", sa.DateTime(), nullable=True),
            sa.Column(
                "status", sa.String(length=40), nullable=False, server_default="QUEUED"
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("file_count", sa.Integer(), nullable=True),
            sa.Column("byte_count", sa.BigInteger(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "created_by",
                GUID(),
                sa.ForeignKey(
                    "user.id",
                    name="fk_airgap_ingestion_run_created_by",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )

    if not insp.has_table("airgap_local_repository"):
        op.create_table(
            "airgap_local_repository",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column("distro", sa.String(length=40), nullable=False),
            sa.Column("version", sa.String(length=40), nullable=False),
            sa.Column("repo_url", sa.String(length=500), nullable=False),
            sa.Column(
                "last_ingest_run_id",
                GUID(),
                sa.ForeignKey(
                    "airgap_ingestion_run.id",
                    name="fk_airgap_local_repository_last_ingest",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.Column("last_ingest_at", sa.DateTime(), nullable=True),
            sa.Column("package_count", sa.Integer(), nullable=True),
            sa.UniqueConstraint(
                "distro", "version",
                name="uq_airgap_local_repository_distro_version",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("airgap_local_repository"):
        op.drop_table("airgap_local_repository")
    if insp.has_table("airgap_ingestion_run"):
        op.drop_table("airgap_ingestion_run")
