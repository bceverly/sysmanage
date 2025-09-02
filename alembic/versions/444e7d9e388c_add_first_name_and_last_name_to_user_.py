"""Add first_name and last_name to user table

Revision ID: 444e7d9e388c
Revises: 1b22c83587b4
Create Date: 2025-09-01 16:37:07.491241

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '444e7d9e388c'
down_revision: Union[str, None] = '1b22c83587b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add first_name and last_name columns to the user table
    op.add_column('user', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('user', sa.Column('last_name', sa.String(length=100), nullable=True))


def downgrade() -> None:
    # Remove first_name and last_name columns from the user table
    op.drop_column('user', 'last_name')
    op.drop_column('user', 'first_name')
