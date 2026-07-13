"""create advisory/errata catalog tables in the shared partition (Phase 14.1)

Vendor advisories (USN / RHSA / SUSE-SU / DSA / FreeBSD-SA) are global reference
data — identical for every tenant — so the catalog lives ONCE in the ``shared``
partition, exactly like CVE data.  Brand-new tables (nothing to rename), created
idempotently:

  * ``shared_advisory`` — the advisory.
  * ``shared_advisory_package`` — fixed packages per OS release (FK to advisory).
  * ``shared_advisory_cve`` — advisory↔CVE links (FKs to advisory AND
    ``shared_vulnerability`` — same partition, so real FKs are fine).
  * ``shared_advisory_ingestion_log`` / ``shared_advisory_refresh_settings`` —
    server-global ingestion bookkeeping (mirrors the CVE equivalents).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s3sharedadv
Revises: s2sharedcve
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "s3sharedadv"
down_revision: Union[str, None] = "s2sharedcve"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_ADVISORY = "shared_advisory"
_ADVISORY_PACKAGE = "shared_advisory_package"
_ADVISORY_CVE = "shared_advisory_cve"
_INGESTION_LOG = "shared_advisory_ingestion_log"
_REFRESH_SETTINGS = "shared_advisory_refresh_settings"


def _ts_columns():
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _ADVISORY not in names:
        op.create_table(
            _ADVISORY,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("advisory_id", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column(
                "advisory_type",
                sa.String(length=20),
                nullable=False,
                server_default="security",
            ),
            sa.Column("severity", sa.String(length=20), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("affected_releases", sa.JSON(), nullable=True),
            sa.Column("references", sa.JSON(), nullable=True),
            sa.Column("published_date", sa.DateTime(), nullable=True),
            sa.Column("modified_date", sa.DateTime(), nullable=True),
            *_ts_columns(),
            sa.UniqueConstraint(
                "source", "advisory_id", name="uq_shared_advisory_src_id"
            ),
        )
        op.create_index("ix_shared_advisory_advisory_id", _ADVISORY, ["advisory_id"])
        op.create_index("ix_shared_advisory_source", _ADVISORY, ["source"])
        op.create_index(
            "ix_shared_advisory_advisory_type", _ADVISORY, ["advisory_type"]
        )
        op.create_index("ix_shared_advisory_severity", _ADVISORY, ["severity"])

    if _ADVISORY_PACKAGE not in names:
        op.create_table(
            _ADVISORY_PACKAGE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("advisory_row_id", GUID(), nullable=False),
            sa.Column("package_name", sa.String(length=255), nullable=False),
            sa.Column("package_manager", sa.String(length=50), nullable=False),
            sa.Column("release", sa.String(length=100), nullable=True),
            sa.Column("fixed_version", sa.String(length=100), nullable=True),
            sa.Column("source", sa.String(length=100), nullable=True),
            *_ts_columns(),
            sa.ForeignKeyConstraint(
                ["advisory_row_id"], ["shared_advisory.id"], ondelete="CASCADE"
            ),
        )
        op.create_index(
            "ix_shared_advisory_package_advisory_row_id",
            _ADVISORY_PACKAGE,
            ["advisory_row_id"],
        )
        op.create_index(
            "ix_shared_advisory_package_package_name",
            _ADVISORY_PACKAGE,
            ["package_name"],
        )
        op.create_index(
            "ix_shared_advisory_package_package_manager",
            _ADVISORY_PACKAGE,
            ["package_manager"],
        )
        op.create_index(
            "ix_shared_advisory_package_release", _ADVISORY_PACKAGE, ["release"]
        )

    if _ADVISORY_CVE not in names:
        op.create_table(
            _ADVISORY_CVE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("advisory_row_id", GUID(), nullable=False),
            sa.Column("vulnerability_id", GUID(), nullable=True),
            sa.Column("cve_id", sa.String(length=20), nullable=False),
            sa.ForeignKeyConstraint(
                ["advisory_row_id"], ["shared_advisory.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["vulnerability_id"],
                ["shared_vulnerability.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "advisory_row_id", "cve_id", name="uq_shared_advisory_cve"
            ),
        )
        op.create_index(
            "ix_shared_advisory_cve_advisory_row_id",
            _ADVISORY_CVE,
            ["advisory_row_id"],
        )
        op.create_index(
            "ix_shared_advisory_cve_vulnerability_id",
            _ADVISORY_CVE,
            ["vulnerability_id"],
        )
        op.create_index("ix_shared_advisory_cve_cve_id", _ADVISORY_CVE, ["cve_id"])

    if _INGESTION_LOG not in names:
        op.create_table(
            _INGESTION_LOG,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("advisories_processed", sa.Integer(), nullable=True),
            sa.Column("packages_processed", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_shared_advisory_ingestion_log_source", _INGESTION_LOG, ["source"]
        )

    if _REFRESH_SETTINGS not in names:
        op.create_table(
            _REFRESH_SETTINGS,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "refresh_interval_hours",
                sa.Integer(),
                nullable=False,
                server_default="24",
            ),
            sa.Column("enabled_sources", sa.JSON(), nullable=False),
            sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
            sa.Column("next_refresh_at", sa.DateTime(), nullable=True),
            *_ts_columns(),
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    # Reverse of the create set (children before parents).
    for table in (
        _REFRESH_SETTINGS,
        _INGESTION_LOG,
        _ADVISORY_CVE,
        _ADVISORY_PACKAGE,
        _ADVISORY,
    ):
        if table in names:
            op.drop_table(table)
