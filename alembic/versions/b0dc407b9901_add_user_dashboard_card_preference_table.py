"""add_user_dashboard_card_preference_table

Revision ID: b0dc407b9901
Revises: f9c0314521b9
Create Date: 2025-10-10 21:19:14.953499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0dc407b9901'
down_revision: Union[str, None] = 'f9c0314521b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_dashboard_card_preference table
    op.create_table(
        'user_dashboard_card_preference',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('card_identifier', sa.String(length=100), nullable=False),
        sa.Column('visible', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop user_dashboard_card_preference table
    op.drop_table('user_dashboard_card_preference')
