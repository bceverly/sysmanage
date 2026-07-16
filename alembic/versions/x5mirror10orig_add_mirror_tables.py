# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add repository-mirroring tables (Phase 10.4)

Revision ID: x5mirror10orig
Revises: w4mfa01enroll
Create Date: 2026-05-07 19:00:00.000000

Three new tables backing the Pro+ ``repository_mirroring_engine``:

  mirror_repository
      One row per mirrored upstream — config + per-row execution
      state.  Foreign-keyed to ``host`` (the agent that runs the
      sync plan owns the on-disk tree).

  mirror_snapshot
      Per-snapshot record (one row per ``rsync`` to ``.snapshots/``).
      Cascades on repo delete.

  mirror_settings
      Singleton admin-controlled defaults — seeded with sensible
      values (mirror_root=/var/mirror, 24-hour integrity cadence,
      30-day retention, no default bandwidth cap, keep 10 snapshots).

Idempotent — re-running ``alembic upgrade head`` is a no-op via
``inspect().has_table()``.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "x5mirror10orig"
down_revision: Union[str, None] = "w4mfa01enroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SINGLETON_MIRROR_SETTINGS_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("mirror_repository"):
        op.create_table(
            "mirror_repository",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("package_manager", sa.String(length=20), nullable=False),
            sa.Column("upstream_url", sa.String(length=500), nullable=False),
            sa.Column("suite", sa.String(length=80), nullable=True),
            sa.Column("components", sa.String(length=200), nullable=True),
            sa.Column("architectures", sa.String(length=120), nullable=True),
            sa.Column("repoid", sa.String(length=120), nullable=True),
            sa.Column("gpgkey_url", sa.String(length=500), nullable=True),
            sa.Column("repo_alias", sa.String(length=120), nullable=True),
            sa.Column("release", sa.String(length=80), nullable=True),
            sa.Column("signing_key_url", sa.String(length=500), nullable=True),
            sa.Column(
                "bandwidth_cap_kbps",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "sync_cron",
                sa.String(length=120),
                nullable=False,
                server_default="0 4 * * *",
            ),
            sa.Column("network_tier", sa.String(length=40), nullable=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_sync_status", sa.String(length=40), nullable=True),
            sa.Column("last_sync_error", sa.Text(), nullable=True),
            sa.Column("next_sync_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("name", name="uq_mirror_repository_name"),
        )

    if not insp.has_table("mirror_snapshot"):
        op.create_table(
            "mirror_snapshot",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "repository_id",
                GUID(),
                sa.ForeignKey("mirror_repository.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("snapshot_id", sa.String(length=80), nullable=False),
            sa.Column("taken_at", sa.DateTime(), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("file_count", sa.Integer(), nullable=True),
            sa.Column("manifest", sa.JSON(), nullable=True),
            sa.Column("retention_until", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    if not insp.has_table("mirror_settings"):
        op.create_table(
            "mirror_settings",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "mirror_root_path",
                sa.String(length=500),
                nullable=False,
                server_default="/var/mirror",
            ),
            sa.Column(
                "integrity_check_cadence_hours",
                sa.Integer(),
                nullable=False,
                server_default="24",
            ),
            sa.Column(
                "retention_window_days",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "default_bandwidth_cap_kbps",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "snapshot_count_to_keep",
                sa.Integer(),
                nullable=False,
                server_default="10",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "updated_by",
                GUID(),
                sa.ForeignKey("user.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                "INSERT INTO mirror_settings "
                "(id, mirror_root_path, integrity_check_cadence_hours, "
                "retention_window_days, default_bandwidth_cap_kbps, "
                "snapshot_count_to_keep) "
                "VALUES (:id, :root, :cadence, :retention, :cap, :keep)"
            ).bindparams(
                # psycopg3 sends parameters with explicit types, so a stringified
                # UUID is rejected by a uuid column (psycopg2 coerced it silently).
                # Bind with the GUID type so it goes over as a real uuid.
                sa.bindparam("id", _SINGLETON_MIRROR_SETTINGS_ID, type_=GUID()),
                root="/var/mirror",
                cadence=24,
                retention=30,
                cap=0,
                keep=10,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("mirror_settings"):
        op.drop_table("mirror_settings")
    if insp.has_table("mirror_snapshot"):
        op.drop_table("mirror_snapshot")
    if insp.has_table("mirror_repository"):
        op.drop_table("mirror_repository")
