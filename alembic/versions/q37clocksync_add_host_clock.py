# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add host clock columns + host_clock_sample (Phase 23.3 S2)

The server's own measurement of each host's clock offset (``clock_*``), what
the host's time service claims (``time_*``), and a 15-minute history of the
measured offset for the host page's chart.

Additive; idempotent; safe on SQLite + PostgreSQL.

Revision ID: q37clocksync
Revises: q36assettagrole
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q37clocksync"
down_revision: Union[str, None] = "q36assettagrole"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "host_clock_sample"
_INDEX = "ix_host_clock_sample_host_time"
_HOST_COLUMNS = (
    ("clock_offset_ms", sa.Float()),
    ("clock_rtt_ms", sa.Float()),
    ("clock_samples", sa.Integer()),
    ("clock_method", sa.String(16)),
    ("clock_measured_at", sa.DateTime()),
    ("time_service", sa.String(16)),
    ("time_service_running", sa.Boolean()),
    ("time_synchronized", sa.Boolean()),
    ("time_source", sa.String(255)),
    ("time_stratum", sa.Integer()),
    ("time_reported_offset_ms", sa.Float()),
    ("time_status_at", sa.DateTime()),
)


def upgrade() -> None:
    bind = op.get_bind()
    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    for name, coltype in _HOST_COLUMNS:
        if name not in host_columns:
            op.add_column("host", sa.Column(name, coltype, nullable=True))
    if _TABLE not in set(inspect(bind).get_table_names()):
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("measured_at", sa.DateTime(), nullable=False),
            sa.Column("offset_ms", sa.Float(), nullable=False),
            sa.Column("rtt_ms", sa.Float(), nullable=True),
            sa.Column("method", sa.String(16), nullable=False),
        )
    indexes = {ix["name"] for ix in inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        op.create_index(_INDEX, _TABLE, ["host_id", "measured_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE in set(inspect(bind).get_table_names()):
        op.drop_table(_TABLE)
    host_columns = {c["name"] for c in inspect(bind).get_columns("host")}
    with op.batch_alter_table("host") as batch:
        for name, _coltype in reversed(_HOST_COLUMNS):
            if name in host_columns:
                batch.drop_column(name)
