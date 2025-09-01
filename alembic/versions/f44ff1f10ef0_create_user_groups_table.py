"""Create user_groups table

Revision ID: f44ff1f10ef0
Revises: 6e3799e9d653
Create Date: 2025-08-31 16:28:25.191870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f44ff1f10ef0'
down_revision: Union[str, None] = '6e3799e9d653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_groups table
    op.create_table('user_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('host_id', sa.Integer(), nullable=False),
        sa.Column('group_name', sa.String(length=255), nullable=False),
        sa.Column('gid', sa.Integer(), nullable=True),  # Linux/macOS group ID
        sa.Column('is_system_group', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_groups_host_id'), 'user_groups', ['host_id'], unique=False)
    op.create_index(op.f('ix_user_groups_group_name'), 'user_groups', ['group_name'], unique=False)


def downgrade() -> None:
    # Drop user_groups table
    op.drop_index(op.f('ix_user_groups_group_name'), table_name='user_groups')
    op.drop_index(op.f('ix_user_groups_host_id'), table_name='user_groups')
    op.drop_table('user_groups')
