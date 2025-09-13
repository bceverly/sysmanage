"""add_tags_and_host_tags_tables

Revision ID: 63b0253b9c9c
Revises: 8a32d1751092
Create Date: 2025-01-10 12:49:58.327638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63b0253b9c9c'
down_revision: Union[str, None] = '8a32d1751092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tags table
    op.create_table('tags',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_tags_name'), 'tags', ['name'], unique=True)

    # Create host_tags junction table (many-to-many relationship)
    op.create_table('host_tags',
        sa.Column('host_id', sa.BigInteger(), nullable=False),
        sa.Column('tag_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('host_id', 'tag_id')
    )
    op.create_index(op.f('ix_host_tags_host_id'), 'host_tags', ['host_id'], unique=False)
    op.create_index(op.f('ix_host_tags_tag_id'), 'host_tags', ['tag_id'], unique=False)


def downgrade() -> None:
    # Drop host_tags table
    op.drop_index(op.f('ix_host_tags_tag_id'), table_name='host_tags')
    op.drop_index(op.f('ix_host_tags_host_id'), table_name='host_tags')
    op.drop_table('host_tags')

    # Drop tags table
    op.drop_index(op.f('ix_tags_name'), table_name='tags')
    op.drop_table('tags')