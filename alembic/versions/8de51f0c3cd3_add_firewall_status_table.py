"""add_firewall_status_table

Revision ID: 8de51f0c3cd3
Revises: b0dc407b9901
Create Date: 2025-10-11 06:51:25.245997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8de51f0c3cd3'
down_revision: Union[str, None] = 'b0dc407b9901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create firewall_status table
    op.create_table(
        'firewall_status',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('host_id', sa.UUID(), nullable=False),
        sa.Column('firewall_name', sa.String(length=255), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tcp_open_ports', sa.Text(), nullable=True),
        sa.Column('udp_open_ports', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_firewall_status_host_id'), 'firewall_status', ['host_id'], unique=False)


def downgrade() -> None:
    # Drop firewall_status table
    op.drop_index(op.f('ix_firewall_status_host_id'), table_name='firewall_status')
    op.drop_table('firewall_status')
