"""Create storage_devices table

Revision ID: ea048a322866
Revises: b3b8489f432c
Create Date: 2025-08-30 08:22:07.461401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea048a322866'
down_revision: Union[str, None] = 'b3b8489f432c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create storage_devices table
    op.create_table(
        'storage_devices',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('host_id', sa.Integer(), sa.ForeignKey('host.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('device_path', sa.String(255), nullable=True),
        sa.Column('mount_point', sa.String(255), nullable=True),
        sa.Column('file_system', sa.String(100), nullable=True),
        sa.Column('device_type', sa.String(100), nullable=True),
        sa.Column('capacity_bytes', sa.BigInteger(), nullable=True),
        sa.Column('used_bytes', sa.BigInteger(), nullable=True),
        sa.Column('available_bytes', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create index on host_id for efficient queries
    op.create_index('idx_storage_devices_host_id', 'storage_devices', ['host_id'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_storage_devices_host_id', table_name='storage_devices')

    # Drop table
    op.drop_table('storage_devices')
