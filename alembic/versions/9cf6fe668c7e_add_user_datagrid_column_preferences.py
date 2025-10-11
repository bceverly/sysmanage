"""add_user_datagrid_column_preferences

Revision ID: 9cf6fe668c7e
Revises: b6bc7ac57c9f
Create Date: 2025-10-08 11:08:24.337322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9cf6fe668c7e'
down_revision: Union[str, None] = 'b6bc7ac57c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'user_datagrid_column_preferences' not in inspector.get_table_names():
        op.create_table(
            'user_datagrid_column_preferences',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('grid_identifier', sa.String(length=255), nullable=False),
            sa.Column('hidden_columns', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        )
        op.create_index(
            op.f('ix_user_datagrid_column_preferences_user_id_grid'),
            'user_datagrid_column_preferences',
            ['user_id', 'grid_identifier'],
            unique=True
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_datagrid_column_preferences_user_id_grid'), table_name='user_datagrid_column_preferences')
    op.drop_table('user_datagrid_column_preferences')
