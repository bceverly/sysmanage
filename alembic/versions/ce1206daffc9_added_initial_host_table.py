"""Added initial host table

Revision ID: ce1206daffc9
Revises: 978c0cbfecb7
Create Date: 2024-05-14 10:59:46.819091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce1206daffc9'
down_revision: Union[str, None] = '978c0cbfecb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('host',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=True),
    sa.Column('fqdn', sa.String(), nullable=True),
    sa.Column('ipv4', sa.String(), nullable=True),
    sa.Column('ipv6', sa.String(), nullable=True),
    sa.Column('last_access', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_host_fqdn'), 'host', ['fqdn'], unique=False)
    op.create_index(op.f('ix_host_id'), 'host', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_host_id'), table_name='host')
    op.drop_index(op.f('ix_host_fqdn'), table_name='host')
    op.drop_table('host')
    # ### end Alembic commands ###
