"""Add missing user table columns: is_admin, last_login_at, created_at, updated_at

Revision ID: 3dfb05070be1
Revises: fb5228fc17fe
Create Date: 2025-09-21 10:09:40.184234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3dfb05070be1'
down_revision: Union[str, None] = 'fb5228fc17fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to user table only if they don't exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    # Get existing columns
    existing_columns = {col['name'] for col in inspector.get_columns('user')}

    # Only add columns that don't exist
    if 'is_admin' not in existing_columns:
        op.add_column('user', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
    if 'last_login_at' not in existing_columns:
        op.add_column('user', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
    if 'created_at' not in existing_columns:
        op.add_column('user', sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
    if 'updated_at' not in existing_columns:
        op.add_column('user', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))


def downgrade() -> None:
    # Remove the columns we added
    op.drop_column('user', 'updated_at')
    op.drop_column('user', 'created_at')
    op.drop_column('user', 'last_login_at')
    op.drop_column('user', 'is_admin')
