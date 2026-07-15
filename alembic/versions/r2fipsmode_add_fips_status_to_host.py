"""add FIPS compliance-mode status to host (tenant partition) — Phase 14.4

Per-host FIPS mode is operational state, so it lives on the ``host`` table in
the TENANT partition (like the 14.3 release-upgrade job).  Detection ("is FIPS
on?") is reported by every agent (OSS); the enable/disable action is
Enterprise-gated (``FIPS_MODE``).

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: r2fipsmode
Revises: r1relupgrade
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "r2fipsmode"
down_revision: Union[str, None] = "r1relupgrade"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host"

# (name, type) for each added column.
_COLUMNS = (
    ("fips_status", sa.String(length=20)),
    ("fips_enabled", sa.Boolean()),
    ("fips_available", sa.Boolean()),
    ("fips_kernel_enforced", sa.Boolean()),
    ("fips_vendor", sa.String(length=50)),
    ("fips_package_version", sa.String(length=100)),
    ("fips_updated_at", sa.DateTime()),
)


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, coltype in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return
    existing = {c["name"] for c in insp.get_columns(_TABLE)}
    for name, _coltype in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
