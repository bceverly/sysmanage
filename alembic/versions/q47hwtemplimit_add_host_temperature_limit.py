# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""host.hardware_temp_warning_c: a per-host temperature warning limit (2026-10-19)

Tenant data.  NULL (the default) keeps judging each temperature sensor
against the limit its own hardware declares.  A value replaces that "high"
limit for every sensor on the host -- for machines that run hot by design,
such as laptops serving with their lids closed.  The device's critical limit
always still applies.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q47hwtemplimit
Revises: q46compevid
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q47hwtemplimit"
down_revision: Union[str, None] = "q46compevid"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMN = "hardware_temp_warning_c"


def _host_columns():
    insp = inspect(op.get_bind())
    if "host" not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns("host")}


def upgrade() -> None:
    columns = _host_columns()
    if columns is not None and _COLUMN not in columns:
        op.add_column("host", sa.Column(_COLUMN, sa.Float(), nullable=True))


def downgrade() -> None:
    columns = _host_columns()
    if columns is not None and _COLUMN in columns:
        with op.batch_alter_table("host") as batch:
            batch.drop_column(_COLUMN)
