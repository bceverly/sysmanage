# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add version column to airgap_bundle.

Revision ID: s9abver
Revises: r8abld
Create Date: 2026-05-25 09:00:00.000000

Captures the upstream sysmanage/sysmanage-agent release version that
went into a given bundle (e.g. "2.4.0.2"), so the UI can display
which build is baked into each ISO.

Reversible — downgrade drops the column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s9abver"
down_revision: Union[str, None] = "r8abld"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "airgap_bundle",
        sa.Column("version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("airgap_bundle", "version")
