"""Increase network interface IP address field lengths

Revision ID: d035c364de42
Revises: ed9659130b39
Create Date: 2025-10-05 10:10:03.314917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd035c364de42'
down_revision: Union[str, None] = 'ed9659130b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Increase IP address field lengths to support IPv6 and extended formats
    op.alter_column('network_interface', 'ipv4_address',
                    existing_type=sa.String(15),
                    type_=sa.String(45),
                    existing_nullable=True)
    op.alter_column('network_interface', 'ipv6_address',
                    existing_type=sa.String(39),
                    type_=sa.String(45),
                    existing_nullable=True)
    op.alter_column('network_interface', 'netmask',
                    existing_type=sa.String(15),
                    type_=sa.String(45),
                    existing_nullable=True)
    op.alter_column('network_interface', 'broadcast',
                    existing_type=sa.String(15),
                    type_=sa.String(45),
                    existing_nullable=True)


def downgrade() -> None:
    # Revert IP address field lengths to original sizes
    op.alter_column('network_interface', 'broadcast',
                    existing_type=sa.String(45),
                    type_=sa.String(15),
                    existing_nullable=True)
    op.alter_column('network_interface', 'netmask',
                    existing_type=sa.String(45),
                    type_=sa.String(15),
                    existing_nullable=True)
    op.alter_column('network_interface', 'ipv6_address',
                    existing_type=sa.String(45),
                    type_=sa.String(39),
                    existing_nullable=True)
    op.alter_column('network_interface', 'ipv4_address',
                    existing_type=sa.String(45),
                    type_=sa.String(15),
                    existing_nullable=True)
