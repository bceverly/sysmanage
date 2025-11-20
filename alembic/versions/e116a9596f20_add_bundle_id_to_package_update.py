"""add_bundle_id_to_package_update

Revision ID: e116a9596f20
Revises: e50d04f81cab
Create Date: 2025-11-19 10:36:36.300877

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e116a9596f20'
down_revision: Union[str, None] = 'e50d04f81cab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column already exists to make this idempotent
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('package_update')]

    # Add bundle_id column to package_update table if it doesn't exist
    if 'bundle_id' not in columns:
        # This stores the actual package identifier needed by package managers (e.g., bundle ID for macOS, app ID for winget)
        op.add_column('package_update',
            sa.Column('bundle_id', sa.String(255), nullable=True)
        )

    # Create index on bundle_id for faster lookups if it doesn't exist
    indexes = [idx['name'] for idx in inspector.get_indexes('package_update')]
    if 'ix_package_update_bundle_id' not in indexes:
        op.create_index('ix_package_update_bundle_id', 'package_update', ['bundle_id'])


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_package_update_bundle_id', 'package_update')

    # Remove bundle_id column
    op.drop_column('package_update', 'bundle_id')
