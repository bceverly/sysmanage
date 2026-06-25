"""drop tenant mirror_known_version (relocated to shared) — Phase 13.1.D

Sibling of the shared-chain ``s1shared`` migration.  ``mirror_known_version`` is
canonical reference data (the version dropdown catalog), identical for every
tenant, so it moves to the ``shared`` partition as ``shared_mirror_known_version``
(created + seeded by ``s1shared``).  This migration removes the per-tenant copy:

  1. Drops the cross-partition foreign key on
     ``mirror_repository.known_version_id`` — the column STAYS as a soft
     reference into the shared catalog (Phase 13.1 rule: no cross-partition FKs).
  2. Drops the now-relocated ``mirror_known_version`` table.

No data is lost: the catalog is migration-seeded reference data (no user rows),
re-seeded in the shared chain.

Idempotent and SQLite + PostgreSQL safe (inspector guards + batch_alter_table for
the SQLite-unfriendly constraint drop).

Revision ID: d1sharedmkv
Revises: q14softpkgprofcreatedby
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "d1sharedmkv"
down_revision: Union[str, None] = "q14softpkgprofcreatedby"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_NAME = "fk_mirror_repository_known_version_id"


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # 1. Drop the cross-partition FK; keep known_version_id as a soft ref.
    #    Discover the FK by the column it constrains, NOT by an assumed name:
    #    PostgreSQL auto-names it ``mirror_repository_known_version_id_fkey``
    #    (ignoring the explicit name the original ADD COLUMN requested), while
    #    SQLite keeps ``fk_mirror_repository_known_version_id`` — so a fixed name
    #    only matches one dialect.  batch_alter_table (recreate='auto') drops it
    #    directly on PostgreSQL and via table-rebuild on SQLite.
    if insp.has_table("mirror_repository"):
        for fk in insp.get_foreign_keys("mirror_repository"):
            cols = fk.get("constrained_columns") or []
            if "known_version_id" in cols or fk.get("referred_table") == (
                "mirror_known_version"
            ):
                fk_name = fk.get("name")
                if fk_name:
                    with op.batch_alter_table("mirror_repository") as batch:
                        # Contract step of the 13.1.D catalog relocation — the
                        # column stays as a soft ref; only the now cross-partition
                        # FK is removed.
                        # expand-contract-ok: relocate mirror_known_version to shared
                        batch.drop_constraint(fk_name, type_="foreignkey")
                break

    # 2. Drop the relocated catalog table (now lives in shared_mirror_known_version).
    if insp.has_table("mirror_known_version"):
        # Migration-seeded reference data, re-created + reseeded in the shared
        # chain (s1shared); the per-tenant copy is intentionally removed here.
        # expand-contract-ok: relocate mirror_known_version to shared
        op.drop_table("mirror_known_version")


def downgrade() -> None:
    """Best-effort structural reversal: recreate the tenant table + FK (without
    reseeding — the canonical data lives in the shared chain now)."""
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("mirror_known_version"):
        op.create_table(
            "mirror_known_version",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("version_key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=200), nullable=False),
            sa.Column("os_family", sa.String(length=40), nullable=False),
            sa.Column("match_regex", sa.String(length=400), nullable=False),
            sa.Column("default_upstream_url", sa.String(length=500), nullable=False),
            sa.Column("default_suite", sa.String(length=80), nullable=True),
            sa.Column("default_repoid", sa.String(length=120), nullable=True),
            sa.Column("default_repo_alias", sa.String(length=120), nullable=True),
            sa.Column("default_release", sa.String(length=80), nullable=True),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=False),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "platform", "version_key", name="uq_mkv_platform_versionkey"
            ),
        )

    if insp.has_table("mirror_repository"):
        fk_names = {fk.get("name") for fk in insp.get_foreign_keys("mirror_repository")}
        if _FK_NAME not in fk_names:
            with op.batch_alter_table("mirror_repository", recreate="auto") as batch:
                batch.create_foreign_key(
                    _FK_NAME,
                    "mirror_known_version",
                    ["known_version_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
