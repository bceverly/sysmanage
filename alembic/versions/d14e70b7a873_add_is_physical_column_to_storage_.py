"""Add is_physical column to storage_devices table

Revision ID: d14e70b7a873
Revises: cb3463447bd4
Create Date: 2025-08-31 06:59:49.458351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd14e70b7a873'
down_revision: Union[str, None] = 'cb3463447bd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_physical column to storage_devices table
    # Default to True for existing data to maintain backward compatibility
    op.add_column('storage_devices', sa.Column('is_physical', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Remove is_physical column from storage_devices table
    op.drop_column('storage_devices', 'is_physical')
