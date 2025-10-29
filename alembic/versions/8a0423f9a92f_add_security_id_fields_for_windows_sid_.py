"""Add security_id fields for Windows SID support

Revision ID: 8a0423f9a92f
Revises: 6dd4ca89b6b8
Create Date: 2025-09-26 09:30:45.866908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a0423f9a92f'
down_revision: Union[str, None] = '6dd4ca89b6b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if columns already exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Add security_id field to user_accounts table for Windows SID storage
    user_accounts_columns = [col['name'] for col in inspector.get_columns('user_accounts')]
    if 'security_id' not in user_accounts_columns:
        op.add_column('user_accounts', sa.Column('security_id', sa.String(255), nullable=True))

    # Add security_id field to user_groups table for Windows SID storage
    user_groups_columns = [col['name'] for col in inspector.get_columns('user_groups')]
    if 'security_id' not in user_groups_columns:
        op.add_column('user_groups', sa.Column('security_id', sa.String(255), nullable=True))


def downgrade() -> None:
    # Remove security_id fields
    op.drop_column('user_groups', 'security_id')
    op.drop_column('user_accounts', 'security_id')
