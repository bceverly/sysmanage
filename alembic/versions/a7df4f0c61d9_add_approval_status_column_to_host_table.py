"""Add approval_status column to host table

Revision ID: a7df4f0c61d9
Revises: 3196f6f22b62
Create Date: 2025-08-28 16:33:51.442819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7df4f0c61d9'
down_revision: Union[str, None] = '3196f6f22b62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('host', sa.Column('approval_status', sa.String(20), nullable=False, server_default='pending'))


def downgrade() -> None:
    op.drop_column('host', 'approval_status')
