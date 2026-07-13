"""create OS lifecycle / EOL registry tables in the shared partition (Phase 14.3)

OS support-lifecycle / EOL data is global reference data (Ubuntu 22.04's EOL is
the same for every customer), so the registry lives ONCE in the ``shared``
partition, like the CVE + advisory catalogs.  Brand-new tables, created
idempotently:

  * ``shared_os_lifecycle`` — per-release lifecycle (release/support/EOL dates,
    LTS, recommended upgrade target).
  * ``shared_os_lifecycle_ingestion_log`` — server-global refresh bookkeeping.

Per-host "approaching EOL" is COMPUTED (join against ``host``), not stored.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: s4oslifecycle
Revises: s3sharedadv
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "s4oslifecycle"
down_revision: Union[str, None] = "s3sharedadv"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_LIFECYCLE = "shared_os_lifecycle"
_INGESTION_LOG = "shared_os_lifecycle_ingestion_log"


def _ts_columns():
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())

    if _LIFECYCLE not in names:
        op.create_table(
            _LIFECYCLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("os_name", sa.String(length=100), nullable=False),
            sa.Column("os_version", sa.String(length=50), nullable=False),
            sa.Column("codename", sa.String(length=100), nullable=True),
            sa.Column("release_date", sa.DateTime(), nullable=True),
            sa.Column("support_end", sa.DateTime(), nullable=True),
            sa.Column("eol_date", sa.DateTime(), nullable=True),
            sa.Column("extended_support_end", sa.DateTime(), nullable=True),
            sa.Column("lts", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("latest_release", sa.String(length=50), nullable=True),
            sa.Column("upgrade_to", sa.String(length=50), nullable=True),
            sa.Column("link", sa.String(length=500), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            *_ts_columns(),
            sa.UniqueConstraint("os_name", "os_version", name="uq_shared_os_lifecycle"),
        )
        op.create_index("ix_shared_os_lifecycle_os_name", _LIFECYCLE, ["os_name"])
        op.create_index("ix_shared_os_lifecycle_os_version", _LIFECYCLE, ["os_version"])
        op.create_index("ix_shared_os_lifecycle_eol_date", _LIFECYCLE, ["eol_date"])

    if _INGESTION_LOG not in names:
        op.create_table(
            _INGESTION_LOG,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("releases_processed", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_shared_os_lifecycle_ingestion_log_source",
            _INGESTION_LOG,
            ["source"],
        )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    names = set(insp.get_table_names())
    for table in (_INGESTION_LOG, _LIFECYCLE):
        if table in names:
            op.drop_table(table)
