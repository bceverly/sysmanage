"""Add hardware inventory fields to host table

Revision ID: b3b8489f432c
Revises: ca5012d6fbb2
Create Date: 2025-08-29 17:21:32.595590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3b8489f432c'
down_revision: Union[str, None] = 'ca5012d6fbb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hardware inventory fields to host table
    op.add_column('host', sa.Column('cpu_vendor', sa.String(length=100), nullable=True))
    op.add_column('host', sa.Column('cpu_model', sa.String(length=200), nullable=True))
    op.add_column('host', sa.Column('cpu_cores', sa.Integer(), nullable=True))
    op.add_column('host', sa.Column('cpu_threads', sa.Integer(), nullable=True))
    op.add_column('host', sa.Column('cpu_frequency_mhz', sa.Integer(), nullable=True))
    op.add_column('host', sa.Column('memory_total_mb', sa.BigInteger(), nullable=True))
    op.add_column('host', sa.Column('storage_details', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('network_details', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('hardware_details', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('hardware_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove hardware inventory fields from host table
    op.drop_column('host', 'hardware_updated_at')
    op.drop_column('host', 'hardware_details')
    op.drop_column('host', 'network_details')
    op.drop_column('host', 'storage_details')
    op.drop_column('host', 'memory_total_mb')
    op.drop_column('host', 'cpu_frequency_mhz')
    op.drop_column('host', 'cpu_threads')
    op.drop_column('host', 'cpu_cores')
    op.drop_column('host', 'cpu_model')
    op.drop_column('host', 'cpu_vendor')
