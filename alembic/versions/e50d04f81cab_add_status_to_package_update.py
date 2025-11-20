"""add_status_to_package_update

Revision ID: e50d04f81cab
Revises: 57f9132b0437
Create Date: 2025-11-19 10:26:20.830539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e50d04f81cab'
down_revision: Union[str, None] = '57f9132b0437'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column already exists to make this idempotent
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('package_update')]

    # Add status column to package_update table if it doesn't exist
    if 'status' not in columns:
        # Status values: 'available', 'updating', 'failed'
        op.add_column('package_update',
            sa.Column('status', sa.String(20), nullable=False, server_default='available')
        )

    # Create index on status for faster queries if it doesn't exist
    indexes = [idx['name'] for idx in inspector.get_indexes('package_update')]
    if 'ix_package_update_status' not in indexes:
        op.create_index('ix_package_update_status', 'package_update', ['status'])


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_package_update_status', 'package_update')

    # Remove status column
    op.drop_column('package_update', 'status')
