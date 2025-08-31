"""Create network_interfaces table

Revision ID: cb3463447bd4
Revises: ea048a322866
Create Date: 2025-08-30 08:24:09.740058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb3463447bd4'
down_revision: Union[str, None] = 'ea048a322866'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create network_interfaces table
    op.create_table(
        'network_interfaces',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('host_id', sa.Integer(), sa.ForeignKey('host.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('interface_type', sa.String(100), nullable=True),
        sa.Column('hardware_type', sa.String(100), nullable=True),
        sa.Column('mac_address', sa.String(17), nullable=True),  # MAC address format: XX:XX:XX:XX:XX:XX
        sa.Column('ipv4_address', sa.String(15), nullable=True),  # IPv4: XXX.XXX.XXX.XXX
        sa.Column('ipv6_address', sa.String(39), nullable=True),  # IPv6: XXXX:XXXX:XXXX:XXXX:XXXX:XXXX:XXXX:XXXX
        sa.Column('subnet_mask', sa.String(15), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=False, nullable=False),
        sa.Column('speed_mbps', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create index on host_id for efficient queries
    op.create_index('idx_network_interfaces_host_id', 'network_interfaces', ['host_id'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_network_interfaces_host_id', table_name='network_interfaces')

    # Drop table
    op.drop_table('network_interfaces')
