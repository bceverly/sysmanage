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
    # Add security_id field to user_accounts table for Windows SID storage
    op.add_column('user_accounts', sa.Column('security_id', sa.String(255), nullable=True))

    # Add security_id field to user_groups table for Windows SID storage
    op.add_column('user_groups', sa.Column('security_id', sa.String(255), nullable=True))


def downgrade() -> None:
    # Remove security_id fields
    op.drop_column('user_groups', 'security_id')
    op.drop_column('user_accounts', 'security_id')
