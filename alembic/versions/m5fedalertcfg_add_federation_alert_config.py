# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add federation_alert_config singleton (Phase 12.1 — configurable thresholds).

Persists operator-chosen thresholds for the three built-in rollup-alert
conditions (site_offline / compliance_below / vulnerabilities_high).  A
single fixed-PK row; all threshold columns nullable so a NULL means "use
the built-in default".  Pure additive ``CREATE TABLE`` — idempotent and
identical on SQLite and PostgreSQL.

Revision ID: m5fedalertcfg
Revises: m4fedconn
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m5fedalertcfg"
down_revision: Union[str, None] = "m4fedconn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "federation_alert_config"


def _guid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID  # noqa: PLC0415

        return UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in set(inspector.get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", _guid_type(), primary_key=True),
        sa.Column("offline_multiplier", sa.Integer(), nullable=True),
        sa.Column("min_offline_seconds", sa.Integer(), nullable=True),
        sa.Column("compliance_threshold", sa.Float(), nullable=True),
        sa.Column("critical_cve_threshold", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in set(inspector.get_table_names()):
        op.drop_table(_TABLE)
