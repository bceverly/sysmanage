"""add mirror_platform_config table + backfill (Phase 10.4.2)

Revision ID: a8mirror30platform
Revises: z7mirror20setup
Create Date: 2026-05-07 22:30:00.000000

Bundles the mirror host + filesystem/retention defaults into a
per-platform row.  Today the platform vocabulary is ``linux`` and
``freebsd`` (more can be added later).  The mirror_repository.host_id
stays on the row for backwards compat but the tab-strip UI reads
host + settings off the platform_config_id FK going forward.

Idempotent + SQLite-safe:

* ``inspect().has_table()`` and ``inspect().get_columns()`` short-circuit
  re-runs of ``alembic upgrade head`` so the migration is a no-op the
  second time.
* ``op.batch_alter_table(recreate='auto')`` is used to add the new FK
  column on SQLite (which can't ADD COLUMN ... REFERENCES inline).  On
  PostgreSQL batch mode is a passthrough and the FK is added inline.
* Backfill uses raw ``text()`` SQL with parameterised values so it
  works against either backend without ORM bootstrap.

Backfill rules:
  - Each existing ``mirror_repository`` row gets a ``platform_config_id``.
  - Mapping: package_manager ∈ {apt, dnf, zypper} → platform ``linux``;
    package_manager == pkg → platform ``freebsd``.
  - One platform_config per (host_id, platform) tuple — multiple
    mirrors sharing a host + platform reuse the same config.
  - Defaults are copied from the singleton ``mirror_settings`` row
    when present, else hardcoded fallbacks (``/var/mirror``, 30-day
    retention, 24-hour integrity cadence, no bandwidth cap, keep 10
    snapshots).
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

from backend.persistence.models.core import GUID

revision: str = "a8mirror30platform"
down_revision: Union[str, None] = "z7mirror20setup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_SETTINGS = {
    "mirror_root_path": "/var/mirror",
    "integrity_check_cadence_hours": 24,
    "retention_window_days": 30,
    "default_bandwidth_cap_kbps": 0,
    "snapshot_count_to_keep": 10,
}


def _platform_for_pm(pm: str) -> str:
    return "freebsd" if (pm or "").lower() == "pkg" else "linux"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # 1. Create mirror_platform_config (idempotent).
    if not insp.has_table("mirror_platform_config"):
        op.create_table(
            "mirror_platform_config",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column(
                "host_id",
                GUID(),
                sa.ForeignKey("host.id", ondelete="CASCADE"),
                nullable=False,
            ),
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
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "platform",
                "host_id",
                name="uq_mirror_platform_config_platform_host",
            ),
        )

    # 2. Add platform_config_id to mirror_repository (idempotent + SQLite-safe).
    if insp.has_table("mirror_repository"):
        existing_cols = {c["name"] for c in insp.get_columns("mirror_repository")}
        if "platform_config_id" not in existing_cols:
            with op.batch_alter_table("mirror_repository", recreate="auto") as batch:
                batch.add_column(
                    sa.Column(
                        "platform_config_id",
                        GUID(),
                        sa.ForeignKey(
                            "mirror_platform_config.id",
                            name="fk_mirror_repository_platform_config_id",
                            ondelete="SET NULL",
                        ),
                        nullable=True,
                    )
                )

    # 3. Backfill defaults from singleton mirror_settings (if any).
    settings_defaults = dict(_DEFAULT_SETTINGS)
    if insp.has_table("mirror_settings"):
        rows = list(
            bind.execute(
                text(
                    "SELECT mirror_root_path, integrity_check_cadence_hours, "
                    "retention_window_days, default_bandwidth_cap_kbps, "
                    "snapshot_count_to_keep FROM mirror_settings LIMIT 1"
                )
            )
        )
        if rows:
            r = rows[0]
            settings_defaults = {
                "mirror_root_path": r[0] or _DEFAULT_SETTINGS["mirror_root_path"],
                "integrity_check_cadence_hours": (
                    r[1] or _DEFAULT_SETTINGS["integrity_check_cadence_hours"]
                ),
                "retention_window_days": (
                    r[2] or _DEFAULT_SETTINGS["retention_window_days"]
                ),
                "default_bandwidth_cap_kbps": (
                    r[3] or _DEFAULT_SETTINGS["default_bandwidth_cap_kbps"]
                ),
                "snapshot_count_to_keep": (
                    r[4] or _DEFAULT_SETTINGS["snapshot_count_to_keep"]
                ),
            }

    # 4. Create one platform_config per (host_id, derived_platform), backfill repos.
    if insp.has_table("mirror_repository"):
        unmigrated = list(
            bind.execute(
                text(
                    "SELECT id, host_id, package_manager FROM mirror_repository "
                    "WHERE platform_config_id IS NULL"
                )
            )
        )
        cache = {}  # (host_id_str, platform) -> cfg_id_str
        for repo_id, host_id, pm in unmigrated:
            platform = _platform_for_pm(pm)
            key = (str(host_id), platform)
            if key in cache:
                cfg_id = cache[key]
            else:
                existing = list(
                    bind.execute(
                        text(
                            "SELECT id FROM mirror_platform_config "
                            "WHERE host_id = :host_id AND platform = :platform"
                        ),
                        {"host_id": host_id, "platform": platform},
                    )
                )
                if existing:
                    cfg_id = str(existing[0][0])
                else:
                    cfg_id = str(uuid.uuid4())
                    bind.execute(
                        text(
                            "INSERT INTO mirror_platform_config "
                            "(id, platform, host_id, mirror_root_path, "
                            " integrity_check_cadence_hours, retention_window_days, "
                            " default_bandwidth_cap_kbps, snapshot_count_to_keep) "
                            "VALUES (:id, :platform, :host_id, :mrp, "
                            " :ich, :rwd, :dbc, :scn)"
                        ),
                        {
                            "id": cfg_id,
                            "platform": platform,
                            "host_id": host_id,
                            "mrp": settings_defaults["mirror_root_path"],
                            "ich": settings_defaults["integrity_check_cadence_hours"],
                            "rwd": settings_defaults["retention_window_days"],
                            "dbc": settings_defaults["default_bandwidth_cap_kbps"],
                            "scn": settings_defaults["snapshot_count_to_keep"],
                        },
                    )
                cache[key] = cfg_id
            bind.execute(
                text(
                    "UPDATE mirror_repository SET platform_config_id = :cfg_id "
                    "WHERE id = :repo_id"
                ),
                {"cfg_id": cfg_id, "repo_id": repo_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("mirror_repository"):
        existing_cols = {c["name"] for c in insp.get_columns("mirror_repository")}
        if "platform_config_id" in existing_cols:
            with op.batch_alter_table("mirror_repository", recreate="auto") as batch:
                batch.drop_column("platform_config_id")
    if insp.has_table("mirror_platform_config"):
        op.drop_table("mirror_platform_config")
