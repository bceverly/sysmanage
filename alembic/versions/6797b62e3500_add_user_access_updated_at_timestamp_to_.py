"""add_user_access_updated_at_timestamp_to_host_table

Revision ID: 6797b62e3500
Revises: cac0bc1b2657
Create Date: 2025-09-09 14:17:36.810047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6797b62e3500'
down_revision: Union[str, None] = 'cac0bc1b2657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add user_access_updated_at timestamp column to host table
    op.add_column('host', sa.Column('user_access_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove user_access_updated_at column from host table
    op.drop_column('host', 'user_access_updated_at')
