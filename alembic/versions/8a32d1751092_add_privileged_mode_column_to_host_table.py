"""add_privileged_mode_column_to_host_table

Revision ID: 8a32d1751092
Revises: dc5ef218e166
Create Date: 2025-09-10 08:36:03.126030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a32d1751092'
down_revision: Union[str, None] = 'dc5ef218e166'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_agent_privileged column to host table
    op.add_column('host', sa.Column('is_agent_privileged', sa.Boolean(), nullable=True, default=False))


def downgrade() -> None:
    # Remove is_agent_privileged column from host table
    op.drop_column('host', 'is_agent_privileged')
