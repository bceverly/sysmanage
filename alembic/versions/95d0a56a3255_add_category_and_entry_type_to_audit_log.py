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
    # Add category column
    op.add_column('audit_log', sa.Column('category', sa.String(length=50), nullable=True))

    # Add entry_type column
    op.add_column('audit_log', sa.Column('entry_type', sa.String(length=50), nullable=True))

    # Add indexes for better query performance
    op.create_index('ix_audit_log_category', 'audit_log', ['category'])
    op.create_index('ix_audit_log_entry_type', 'audit_log', ['entry_type'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_audit_log_entry_type', table_name='audit_log')
    op.drop_index('ix_audit_log_category', table_name='audit_log')

    # Drop columns
    op.drop_column('audit_log', 'entry_type')
    op.drop_column('audit_log', 'category')
