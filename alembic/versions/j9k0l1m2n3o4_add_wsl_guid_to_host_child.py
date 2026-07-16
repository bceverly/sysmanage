# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Add wsl_guid column to host_child table for stale message prevention

Revision ID: j9k0l1m2n3o4
Revises: i8j9k0l1m2n3
Create Date: 2025-12-04 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j9k0l1m2n3o4"
down_revision: Union[str, None] = "i8j9k0l1m2n3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add wsl_guid column to host_child table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if column already exists (idempotent)
    columns = [col["name"] for col in inspector.get_columns("host_child")]
    if "wsl_guid" not in columns:
        # Add nullable column for WSL GUID
        # This is the unique identifier assigned by Windows to each WSL instance
        # Used to prevent stale delete commands from affecting newly created instances
        op.add_column(
            "host_child",
            sa.Column("wsl_guid", sa.String(36), nullable=True),
        )


def downgrade() -> None:
    """Remove wsl_guid column from host_child table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if column exists before dropping
    columns = [col["name"] for col in inspector.get_columns("host_child")]
    if "wsl_guid" in columns:
        op.drop_column("host_child", "wsl_guid")
