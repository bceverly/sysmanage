# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The devices the new-device alert has decided on (ROADMAP 26.9).

``new_device_alert_mark``: one row per alert rule and device, so a device
is new once -- alerted on, or left out, and never considered again.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q93newdevicealert
Revises: q92airgapburnset
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op
from backend.persistence.models.core import GUID

revision: str = "q93newdevicealert"
down_revision: Union[str, None] = "q92airgapburnset"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_TABLE = "new_device_alert_mark"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE in inspector.get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "rule_id",
            GUID(),
            sa.ForeignKey("alert_rule.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("ips", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("rule_id", "identity", name="uq_new_device_alert_mark"),
    )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _TABLE in inspector.get_table_names():
        op.drop_table(_TABLE)
