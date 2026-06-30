"""Move CVE reference tables into the shared partition (option B).

CVE data is global platform truth — identical for every tenant — so it belongs
in the ``shared`` partition, not per-tenant.  This relocates the CVE reference +
config tables to the ``shared_*`` prefix.

Unlike ``shared_mirror_known_version`` (seedable catalog), CVE rows are fetched
external data (NVD/Ubuntu/...), so they must be **preserved**, not re-seeded:

  * **Existing deployment** — the old unprefixed table exists (populated), so it
    is renamed in place to ``shared_*`` (rows preserved).
  * **Fresh install** — no old table to rename, so an empty ``shared_*`` table is
    created (the CVE refresh pipeline populates it on first run).

This chain runs BEFORE the tenant chain (see ``sysmanage_migrate.py``), so on the
bootstrap/collapsed database the rename happens before the tenant chain's drop
touches the same tables — populated CVE data is never dropped.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s2sharedcve
Revises: s1shared
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "s2sharedcve"
down_revision: Union[str, None] = "s1shared"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


# (old unprefixed name, new shared_* name)
_RENAMES = (
    ("vulnerability", "shared_vulnerability"),
    ("package_vulnerability", "shared_package_vulnerability"),
    ("vulnerability_ingestion_log", "shared_vulnerability_ingestion_log"),
    ("cve_refresh_settings", "shared_cve_refresh_settings"),
)


def _ts_columns():
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _create_shared_tables(names):
    """Create any still-missing shared_* CVE tables (fresh-install path)."""
    if "shared_vulnerability" not in names:
        op.create_table(
            "shared_vulnerability",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("cve_id", sa.String(length=20), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("cvss_score", sa.String(length=10), nullable=True),
            sa.Column("cvss_version", sa.String(length=10), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=True),
            sa.Column("published_date", sa.DateTime(), nullable=True),
            sa.Column("modified_date", sa.DateTime(), nullable=True),
            sa.Column("references", sa.JSON(), nullable=True),
            sa.Column("affected_systems", sa.JSON(), nullable=True),
            *_ts_columns(),
        )
        op.create_index(
            "ix_shared_vulnerability_cve_id",
            "shared_vulnerability",
            ["cve_id"],
            unique=True,
        )

    if "shared_package_vulnerability" not in names:
        op.create_table(
            "shared_package_vulnerability",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "vulnerability_id",
                GUID(),
                sa.ForeignKey("shared_vulnerability.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("package_name", sa.String(length=255), nullable=False),
            sa.Column("package_manager", sa.String(length=50), nullable=False),
            sa.Column("vulnerable_versions", sa.String(length=500), nullable=True),
            sa.Column("fixed_version", sa.String(length=100), nullable=True),
            sa.Column("advisory_ids", sa.JSON(), nullable=True),
            sa.Column("source", sa.String(length=100), nullable=True),
            *_ts_columns(),
        )
        op.create_index(
            "ix_shared_package_vulnerability_vulnerability_id",
            "shared_package_vulnerability",
            ["vulnerability_id"],
        )
        op.create_index(
            "ix_shared_package_vulnerability_package_name",
            "shared_package_vulnerability",
            ["package_name"],
        )
        op.create_index(
            "ix_shared_package_vulnerability_package_manager",
            "shared_package_vulnerability",
            ["package_manager"],
        )

    if "shared_vulnerability_ingestion_log" not in names:
        op.create_table(
            "shared_vulnerability_ingestion_log",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("vulnerabilities_processed", sa.Integer(), nullable=True),
            sa.Column("packages_processed", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_shared_vulnerability_ingestion_log_source",
            "shared_vulnerability_ingestion_log",
            ["source"],
        )

    if "shared_cve_refresh_settings" not in names:
        op.create_table(
            "shared_cve_refresh_settings",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("refresh_interval_hours", sa.Integer(), nullable=False),
            sa.Column("enabled_sources", sa.JSON(), nullable=False),
            sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
            sa.Column("next_refresh_at", sa.DateTime(), nullable=True),
            sa.Column("nvd_api_key", sa.String(length=255), nullable=True),
            *_ts_columns(),
        )


def upgrade() -> None:
    bind = op.get_bind()
    names = set(inspect(bind).get_table_names())

    # Existing deployments: rename the populated tables in place (preserve rows).
    for old, new in _RENAMES:
        if old in names and new not in names:
            # expand-contract-ok: in-place rename into the shared partition (preserves rows)
            op.rename_table(old, new)

    # Fresh installs (nothing to rename): create empty shared_* tables.
    _create_shared_tables(set(inspect(bind).get_table_names()))


def downgrade() -> None:
    names = set(inspect(op.get_bind()).get_table_names())
    for old, new in _RENAMES:
        if new in names and old not in names:
            # expand-contract-ok: reverse of the shared-partition rename.
            op.rename_table(new, old)
