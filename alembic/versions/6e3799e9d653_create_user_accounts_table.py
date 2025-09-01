"""Create user_accounts table

Revision ID: 6e3799e9d653
Revises: d14e70b7a873
Create Date: 2025-08-31 16:27:23.814907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e3799e9d653'
down_revision: Union[str, None] = 'd14e70b7a873'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_accounts table
    op.create_table('user_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('uid', sa.Integer(), nullable=True),  # Linux/macOS user ID
        sa.Column('home_directory', sa.String(length=500), nullable=True),
        sa.Column('shell', sa.String(length=255), nullable=True),
        sa.Column('is_system_user', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_accounts_host_id'), 'user_accounts', ['host_id'], unique=False)
    op.create_index(op.f('ix_user_accounts_username'), 'user_accounts', ['username'], unique=False)


def downgrade() -> None:
    # Drop user_accounts table
    op.drop_index(op.f('ix_user_accounts_username'), table_name='user_accounts')
    op.drop_index(op.f('ix_user_accounts_host_id'), table_name='user_accounts')
    op.drop_table('user_accounts')
