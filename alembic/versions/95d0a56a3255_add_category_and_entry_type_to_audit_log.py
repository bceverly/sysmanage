"""add_category_and_entry_type_to_audit_log

Revision ID: 95d0a56a3255
Revises: ba7f2eae2c99
Create Date: 2025-10-13 06:48:32.418107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95d0a56a3255'
down_revision: Union[str, None] = 'ba7f2eae2c99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns and indexes already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('audit_log')]
    indexes = inspector.get_indexes('audit_log')
    index_names = [idx['name'] for idx in indexes]

    # Add category column
    if 'category' not in columns:
        op.add_column('audit_log', sa.Column('category', sa.String(length=50), nullable=True))

    # Add entry_type column
    if 'entry_type' not in columns:
        op.add_column('audit_log', sa.Column('entry_type', sa.String(length=50), nullable=True))

    # Add indexes for better query performance
    if 'ix_audit_log_category' not in index_names:
        op.create_index('ix_audit_log_category', 'audit_log', ['category'])
    if 'ix_audit_log_entry_type' not in index_names:
        op.create_index('ix_audit_log_entry_type', 'audit_log', ['entry_type'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_audit_log_entry_type', table_name='audit_log')
    op.drop_index('ix_audit_log_category', table_name='audit_log')

    # Drop columns
    op.drop_column('audit_log', 'entry_type')
    op.drop_column('audit_log', 'category')
