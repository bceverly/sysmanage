"""Add OS version fields to host table

Revision ID: ca5012d6fbb2
Revises: 995799008308
Create Date: 2025-08-29 12:08:55.240100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca5012d6fbb2'
down_revision: Union[str, None] = '995799008308'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add OS version fields to host table
    op.add_column('host', sa.Column('platform', sa.String(50), nullable=True))
    op.add_column('host', sa.Column('platform_release', sa.String(100), nullable=True))
    op.add_column('host', sa.Column('platform_version', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('machine_architecture', sa.String(50), nullable=True))
    op.add_column('host', sa.Column('processor', sa.String(100), nullable=True))
    op.add_column('host', sa.Column('os_details', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('os_version_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove OS version fields from host table
    op.drop_column('host', 'os_version_updated_at')
    op.drop_column('host', 'os_details')
    op.drop_column('host', 'processor')
    op.drop_column('host', 'machine_architecture')
    op.drop_column('host', 'platform_version')
    op.drop_column('host', 'platform_release')
    op.drop_column('host', 'platform')
