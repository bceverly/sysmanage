# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Automatic Ubuntu Pro attach (2026-11-13).

``host.ubuntu_pro_auto_attach_at``: when the server queued this host's one
automatic attach, or first saw it attached; NULL means not yet handled.

Idempotent; safe on SQLite + PostgreSQL.

Revision ID: q90proautoattach
Revises: q89airgaptools
"""

from typing import Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "q90proautoattach"
down_revision: Union[str, None] = "q89airgaptools"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

_HOST = "host"
_COLUMN = "ubuntu_pro_auto_attach_at"


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if _HOST not in inspector.get_table_names():
        return
    if _COLUMN not in {c["name"] for c in inspector.get_columns(_HOST)}:
        op.add_column(_HOST, sa.Column(_COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if _HOST not in inspector.get_table_names():
        return
    if _COLUMN in {c["name"] for c in inspector.get_columns(_HOST)}:
        with op.batch_alter_table(_HOST) as batch:
            batch.drop_column(_COLUMN)
