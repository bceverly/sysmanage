"""Add available_packages table

Revision ID: ad66ac11e167
Revises: 904046eab30e
Create Date: 2025-09-20 07:42:22.696300

"""
from typing import Sequence, Union
import os
import glob

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad66ac11e167'
down_revision: Union[str, None] = '904046eab30e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up orphaned .pyc files from missing migration revisions
    # This addresses the "Can't locate revision identified by '3cc63cc81f0c'" error
    # that can occur when .pyc files exist but the .py source files are missing
    try:
        # Get the directory containing this migration file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        pycache_dir = os.path.join(current_dir, '__pycache__')

        if os.path.exists(pycache_dir):
            # Look for orphaned .pyc files that don't have corresponding .py files
            for pyc_file in glob.glob(os.path.join(pycache_dir, '*.pyc')):
                # Extract revision ID from .pyc filename (format: revision_description.cpython-*.pyc)
                basename = os.path.basename(pyc_file)
                if '_' in basename:
                    revision_part = basename.split('_')[0]
                    # Check if corresponding .py file exists
                    potential_py_files = glob.glob(os.path.join(current_dir, f'{revision_part}_*.py'))
                    if not potential_py_files:
                        print(f"Removing orphaned .pyc file: {pyc_file}")
                        os.remove(pyc_file)
    except Exception as e:
        # Don't fail the migration if cleanup fails
        print(f"Warning: Could not clean up orphaned .pyc files: {e}")

    # Check if table already exists before creating it
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'available_packages' in existing_tables:
        print("Table 'available_packages' already exists, skipping creation")
        return

    # Create available_packages table
    op.create_table('available_packages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('os_name', sa.String(length=100), nullable=False),
        sa.Column('os_version', sa.String(length=100), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_version', sa.String(length=100), nullable=False),
        sa.Column('package_description', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_available_packages_package_name', 'available_packages', ['package_name'])
    op.create_index('ix_available_packages_last_updated', 'available_packages', ['last_updated'])
    op.create_index('ix_available_packages_os_version_pm', 'available_packages', ['os_name', 'os_version', 'package_manager'])
    op.create_index('ix_available_packages_unique', 'available_packages', ['os_name', 'os_version', 'package_manager', 'package_name'], unique=True)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_available_packages_unique', table_name='available_packages')
    op.drop_index('ix_available_packages_os_version_pm', table_name='available_packages')
    op.drop_index('ix_available_packages_last_updated', table_name='available_packages')
    op.drop_index('ix_available_packages_package_name', table_name='available_packages')

    # Drop table
    op.drop_table('available_packages')
