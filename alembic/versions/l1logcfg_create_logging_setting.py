# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""create logging_setting (Phase 13.3 — DB-stored logging configuration)

Server-global logging settings (server row + per-OS-family agent default rows)
editable from the Settings UI and pushed to agents; DB wins over the yaml file.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: l1logcfg
Revises: k1livepatch
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from backend.persistence.models.core import GUID

revision: str = "l1logcfg"
down_revision: Union[str, None] = "k1livepatch"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "logging_setting"


def upgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("os_family", sa.String(length=20), nullable=True),
        sa.Column(
            "native_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "native_target", sa.String(length=20), nullable=False, server_default="auto"
        ),
        sa.Column("native_identifier", sa.String(length=255), nullable=True),
        sa.Column("log_level", sa.String(length=64), nullable=True),
        sa.Column("verbosity", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "os_family", name="uq_logging_scope_os"),
    )


def downgrade() -> None:
    insp = inspect(op.get_bind())
    if insp.has_table(_TABLE):
        # expand-contract-ok: reverse of this revision's create_table.
        op.drop_table(_TABLE)
