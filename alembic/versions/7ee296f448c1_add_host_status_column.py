"""add_host_status_column

Revision ID: 7ee296f448c1
Revises: ce1206daffc9
Create Date: 2025-08-28 07:40:37.113496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ee296f448c1'
down_revision: Union[str, None] = 'ce1206daffc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status column to host table
    op.add_column('host', sa.Column('status', sa.String(20), nullable=False, server_default='up'))


def downgrade() -> None:
    # Remove status column from host table
    op.drop_column('host', 'status')
