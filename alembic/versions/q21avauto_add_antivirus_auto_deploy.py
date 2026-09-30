# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""add antivirus_auto_deploy (Phase 21.3)

Tenant data: what the server last pushed to each host on its own when it
keeps hosts equipped with ClamAV for malware scanning -- the package, the
deploy-plan version and how many times that version was pushed.

Additive. Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q21avauto
Revises: q20malware
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q21avauto"
down_revision: Union[str, None] = "q20malware"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "antivirus_auto_deploy"


def upgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("host_id", GUID(), primary_key=True),
        sa.Column("antivirus_package", sa.String(length=255), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        op.drop_table(_TABLE)
