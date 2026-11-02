# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""host.script_approval_required: the agent runs only approved scripts (2026-11-02)

Tenant data.  Reported by the agent from its own configuration
(``script_execution.security.require_approval``), next to
``script_execution_enabled``.  When true the server refuses one-off script
runs to the host and sends its scripts only through the Professional+
approval workflow; the agent refuses any script without an approval id.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q72scriptapproval
Revises: q71backupnetmounts
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q72scriptapproval"
down_revision: Union[str, None] = "q71backupnetmounts"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_COLUMN = "script_approval_required"


def _host_columns():
    insp = inspect(op.get_bind())
    if "host" not in set(insp.get_table_names()):
        return None
    return {c["name"] for c in insp.get_columns("host")}


def upgrade() -> None:
    columns = _host_columns()
    if columns is not None and _COLUMN not in columns:
        op.add_column(
            "host",
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    columns = _host_columns()
    if columns is not None and _COLUMN in columns:
        with op.batch_alter_table("host") as batch:
            batch.drop_column(_COLUMN)
