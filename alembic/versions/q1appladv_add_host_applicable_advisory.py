"""create host_applicable_advisory (tenant partition) — Phase 14.1

Per-host advisory applicability lives in the TENANT partition (unprefixed).
``advisory_id`` is a SOFT cross-partition reference to ``shared_advisory.id`` —
NO ForeignKey (the shared catalog lives in a different partition/engine under
scale-out), matching ``host_vulnerability_finding.vulnerability_id``.  Advisory
fields are denormalized so the tenant row is useful without a cross-engine join.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q1appladv
Revises: p1maintwin
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "q1appladv"
down_revision: Union[str, None] = "p1maintwin"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host_applicable_advisory"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("host_id", GUID(), nullable=False),
        # SOFT ref to shared_advisory.id — no ForeignKey (cross-partition).
        sa.Column("advisory_id", GUID(), nullable=False),
        sa.Column("advisory_identifier", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("advisory_type", sa.String(length=20), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("installed_version", sa.String(length=100), nullable=True),
        sa.Column("fixed_version", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="applicable",
        ),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # host lives in the tenant partition too → real intra-partition FK.
        sa.ForeignKeyConstraint(["host_id"], ["host.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "host_id",
            "advisory_id",
            "package_name",
            name="uq_host_applicable_advisory",
        ),
    )
    op.create_index("ix_host_applicable_advisory_host_id", _TABLE, ["host_id"])
    op.create_index("ix_host_applicable_advisory_advisory_id", _TABLE, ["advisory_id"])
    op.create_index(
        "ix_host_applicable_advisory_advisory_identifier",
        _TABLE,
        ["advisory_identifier"],
    )
    op.create_index(
        "ix_host_applicable_advisory_advisory_type", _TABLE, ["advisory_type"]
    )
    op.create_index("ix_host_applicable_advisory_severity", _TABLE, ["severity"])
    op.create_index("ix_host_applicable_advisory_status", _TABLE, ["status"])


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        op.drop_table(_TABLE)
