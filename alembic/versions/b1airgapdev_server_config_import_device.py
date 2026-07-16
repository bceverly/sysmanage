# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add server_configuration.airgap_import_device.

Revision ID: b1airgapdev
Revises: a3snapsize
Create Date: 2026-06-02 18:30:00.000000

An Air-Gap Repository server lets the operator pick which block device
(optical/USB) holds the collector media to import.  The choice persists
on the server_configuration singleton so the Air-Gap Repositories page
can enable its Import button against the right drive across restarts.

Nullable String — NULL means "no import device chosen yet".  ADD COLUMN
is supported by both PostgreSQL and SQLite, so no dialect guard needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1airgapdev"
down_revision: Union[str, None] = "a3snapsize"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "server_configuration",
        sa.Column("airgap_import_device", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("server_configuration", "airgap_import_device")
