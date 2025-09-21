"""add_package_update_columns_with_default_values

Revision ID: b68da58d8a5d
Revises: 67a82b319674
Create Date: 2025-09-21 10:30:45.361656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b68da58d8a5d'
down_revision: Union[str, None] = '3dfb05070be1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to package_update table
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    # Check if we need to rename table from package_updates to package_update
    table_names = inspector.get_table_names()
    if 'package_updates' in table_names and 'package_update' not in table_names:
        op.rename_table('package_updates', 'package_update')

    # Now work with package_update table (or package_updates if that's what exists)
    table_name = 'package_update' if 'package_update' in inspector.get_table_names() else 'package_updates'
    if table_name not in inspector.get_table_names():
        # Table doesn't exist, skip this migration
        return

    # Get existing columns
    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}

    # Add nullable columns first only if they don't exist
    if 'priority' not in existing_columns:
        op.add_column(table_name, sa.Column('priority', sa.String(length=20), nullable=True))
    if 'description' not in existing_columns:
        op.add_column(table_name, sa.Column('description', sa.Text(), nullable=True))
    if 'size_bytes' not in existing_columns:
        op.add_column(table_name, sa.Column('size_bytes', sa.BigInteger(), nullable=True))

    # Add timestamp columns with defaults only if they don't exist
    if 'discovered_at' not in existing_columns:
        op.add_column(table_name, sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {table_name} SET discovered_at = NOW() WHERE discovered_at IS NULL")
        op.alter_column(table_name, 'discovered_at', nullable=False)

    if 'created_at' not in existing_columns:
        op.add_column(table_name, sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {table_name} SET created_at = NOW() WHERE created_at IS NULL")
        op.alter_column(table_name, 'created_at', nullable=False)

    # Add update_type column with default, then update existing rows only if it doesn't exist
    if 'update_type' not in existing_columns:
        op.add_column(table_name, sa.Column('update_type', sa.String(length=20), nullable=True))
        op.execute(f"UPDATE {table_name} SET update_type = 'package' WHERE update_type IS NULL")
        op.alter_column(table_name, 'update_type', nullable=False)

    # Remove old columns that aren't in the model (only if they exist)
    columns_to_remove = [
        'detected_at', 'update_size_bytes', 'source', 'last_checked_at',
        'repository', 'bundle_id', 'channel', 'is_system_update', 'status', 'is_security_update'
    ]

    for column in columns_to_remove:
        if column in existing_columns:
            op.drop_column(table_name, column)


def downgrade() -> None:
    # Add back old columns
    op.add_column('package_update', sa.Column('is_security_update', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('package_update', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('package_update', sa.Column('is_system_update', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('package_update', sa.Column('channel', sa.String(length=50), nullable=True))
    op.add_column('package_update', sa.Column('bundle_id', sa.String(length=255), nullable=True))
    op.add_column('package_update', sa.Column('repository', sa.String(length=100), nullable=True))
    op.add_column('package_update', sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
    op.add_column('package_update', sa.Column('source', sa.String(length=100), nullable=True))
    op.add_column('package_update', sa.Column('update_size_bytes', sa.BigInteger(), nullable=True))
    op.add_column('package_update', sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))

    # Remove new columns
    op.drop_column('package_update', 'update_type')
    op.drop_column('package_update', 'priority')
    op.drop_column('package_update', 'description')
    op.drop_column('package_update', 'size_bytes')
    op.drop_column('package_update', 'discovered_at')
    op.drop_column('package_update', 'created_at')

    # Rename table back
    op.rename_table('package_update', 'package_updates')
