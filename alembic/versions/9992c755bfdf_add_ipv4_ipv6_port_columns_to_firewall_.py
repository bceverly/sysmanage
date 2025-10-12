"""add_ipv4_ipv6_port_columns_to_firewall_status

Revision ID: 9992c755bfdf
Revises: d44688bd27aa
Create Date: 2025-10-11 09:55:34.674498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9992c755bfdf'
down_revision: Union[str, None] = 'd44688bd27aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add IPv4 and IPv6 port columns to firewall_status table.
    Keep existing tcp_open_ports and udp_open_ports for backward compatibility,
    but add new columns that separate by IP version and include protocol tags.
    """
    # Add new columns for IPv4 and IPv6 ports
    # Each column stores a JSON array of objects like: [{"port": "22", "protocols": ["tcp"]}, {"port": "8080", "protocols": ["tcp", "udp"]}]
    op.add_column('firewall_status', sa.Column('ipv4_ports', sa.Text(), nullable=True))
    op.add_column('firewall_status', sa.Column('ipv6_ports', sa.Text(), nullable=True))


def downgrade() -> None:
    """
    Remove IPv4 and IPv6 port columns from firewall_status table.
    """
    op.drop_column('firewall_status', 'ipv6_ports')
    op.drop_column('firewall_status', 'ipv4_ports')
