"""add air-gap collector tables (Phase 11.1)

Revision ID: d2airgap10collect
Revises: c1mirror50dropdown
Create Date: 2026-05-10 08:00:00.000000

Three new tables backing the Pro+ ``airgap_collector_engine``:

  airgap_collection_run      — one row per collection job
  airgap_collection_target   — per-distro target list inside a run
  airgap_media_manifest      — produced ISO + signed manifest envelope

Idempotent — re-running ``alembic upgrade head`` is a no-op via
``inspect().has_table()``.

Lessons from Phase 10.5 SQLite breakage applied:
  - Every FK has an explicit ``name=...`` so batch_alter_table works.
  - Tables are created in dependency order; cross-table FKs use the
    ``ForeignKey("table.col", name="fk_...")`` shape so a future
    add_column on these tables can re-route through batch mode without
    needing to add a name retroactively.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "d2airgap10collect"
down_revision: Union[str, None] = "c1mirror50dropdown"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("airgap_collection_run"):
        op.create_table(
            "airgap_collection_run",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column("iso_label", sa.String(length=80), nullable=False),
            sa.Column(
                "media_size_bytes",
                sa.BigInteger(),
                nullable=False,
                server_default="4700000000",
            ),
            sa.Column(
                "include_cve",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "include_compliance",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "status",
                sa.String(length=40),
                nullable=False,
                server_default="QUEUED",
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
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
                    name="fk_airgap_collection_run_created_by",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "iso_label", "created_at",
                name="uq_airgap_collection_run_label_time",
            ),
        )

    if not insp.has_table("airgap_collection_target"):
        op.create_table(
            "airgap_collection_target",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column(
                "run_id",
                GUID(),
                sa.ForeignKey(
                    "airgap_collection_run.id",
                    name="fk_airgap_collection_target_run_id",
                    ondelete="CASCADE",
                ),
                nullable=False,
            ),
            sa.Column("distro", sa.String(length=40), nullable=False),
            sa.Column("version", sa.String(length=40), nullable=False),
            sa.Column("repos", sa.Text(), nullable=True),
            sa.Column("byte_count", sa.BigInteger(), nullable=True),
            sa.Column("file_count", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=True),
        )

    if not insp.has_table("airgap_media_manifest"):
        op.create_table(
            "airgap_media_manifest",
            sa.Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            sa.Column(
                "run_id",
                GUID(),
                sa.ForeignKey(
                    "airgap_collection_run.id",
                    name="fk_airgap_media_manifest_run_id",
                    ondelete="CASCADE",
                ),
                nullable=False,
            ),
            sa.Column("disc_index", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("disc_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("iso_path", sa.String(length=500), nullable=False),
            sa.Column("iso_sha256", sa.String(length=64), nullable=False),
            sa.Column("iso_size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("manifest_json", sa.Text(), nullable=False),
            sa.Column("signature", sa.Text(), nullable=False),
            sa.Column("signer_fingerprint", sa.String(length=128), nullable=False),
            sa.Column(
                "signature_algorithm",
                sa.String(length=40),
                nullable=False,
                server_default="ed25519",
            ),
            sa.Column("format_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "run_id", "disc_index",
                name="uq_airgap_media_manifest_run_disc",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("airgap_media_manifest"):
        op.drop_table("airgap_media_manifest")
    if insp.has_table("airgap_collection_target"):
        op.drop_table("airgap_collection_target")
    if insp.has_table("airgap_collection_run"):
        op.drop_table("airgap_collection_run")
