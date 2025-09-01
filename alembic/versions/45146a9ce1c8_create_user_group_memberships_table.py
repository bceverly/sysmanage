"""Create user_group_memberships table

Revision ID: 45146a9ce1c8
Revises: f44ff1f10ef0
Create Date: 2025-08-31 18:12:01.366602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45146a9ce1c8'
down_revision: Union[str, None] = 'f44ff1f10ef0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_group_memberships table
    op.create_table('user_group_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('user_account_id', sa.Integer(), nullable=False),
        sa.Column('user_group_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_account_id'], ['user_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_group_id'], ['user_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_account_id', 'user_group_id', name='unique_user_group_membership')
    )
    op.create_index(op.f('ix_user_group_memberships_host_id'), 'user_group_memberships', ['host_id'], unique=False)
    op.create_index(op.f('ix_user_group_memberships_user_account_id'), 'user_group_memberships', ['user_account_id'], unique=False)
    op.create_index(op.f('ix_user_group_memberships_user_group_id'), 'user_group_memberships', ['user_group_id'], unique=False)


def downgrade() -> None:
    # Drop user_group_memberships table
    op.drop_index(op.f('ix_user_group_memberships_user_group_id'), table_name='user_group_memberships')
    op.drop_index(op.f('ix_user_group_memberships_user_account_id'), table_name='user_group_memberships')
    op.drop_index(op.f('ix_user_group_memberships_host_id'), table_name='user_group_memberships')
    op.drop_table('user_group_memberships')
