# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""When automatic updates may happen (ROADMAP 26.2 and 26.3, Enterprise).

* ``upgrade_profiles``: ``wait_days_regular`` and ``wait_days_critical``
  (0: no waiting, as 26.1) and ``critical_source`` (which data decides that
  a patch fixes a critical CVE: the vulnerability scans, the vendor
  advisories, or either)
* ``auto_update_settings.critical_threshold``: ``critical`` only, or
  ``high`` and critical

``reboot_mode`` gains ``in_window`` and ``auto_update_run.status`` gains
``waiting``; both columns are already wide enough.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q95autoupdatetiming
Revises: q94autoupdate
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q95autoupdatetiming"
down_revision: Union[str, None] = "q94autoupdate"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _columns():
    return {
        "upgrade_profiles": [
            sa.Column(
                "wait_days_regular", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "wait_days_critical", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "critical_source",
                sa.String(16),
                nullable=False,
                server_default="either",
            ),
        ],
        "auto_update_settings": [
            sa.Column(
                "critical_threshold",
                sa.String(8),
                nullable=False,
                server_default="critical",
            ),
        ],
    }


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in have:
                op.add_column(table, column)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, columns in _columns().items():
        if table not in tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for column in columns:
                if column.name in have:
                    batch.drop_column(column.name)
