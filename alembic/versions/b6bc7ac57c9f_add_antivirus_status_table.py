"""add_antivirus_status_table

Revision ID: b6bc7ac57c9f
Revises: c8f1e65b041e
Create Date: 2025-10-08 10:45:18.889892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6bc7ac57c9f'
down_revision: Union[str, None] = 'c8f1e65b041e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'antivirus_status' not in inspector.get_table_names():
        op.create_table(
            'antivirus_status',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('host_id', sa.UUID(), nullable=False),
            sa.Column('software_name', sa.String(length=255), nullable=True),
            sa.Column('install_path', sa.String(length=512), nullable=True),
            sa.Column('version', sa.String(length=100), nullable=True),
            sa.Column('enabled', sa.Boolean(), nullable=True),
            sa.Column('last_updated', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        )
        op.create_index(op.f('ix_antivirus_status_host_id'), 'antivirus_status', ['host_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_antivirus_status_host_id'), table_name='antivirus_status')
    op.drop_table('antivirus_status')
