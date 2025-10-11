"""add_commercial_antivirus_status_table

Revision ID: 7ee1f0bd6b87
Revises: d4553f53a3c2
Create Date: 2025-10-10 14:09:12.213452

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ee1f0bd6b87'
down_revision: Union[str, None] = 'd4553f53a3c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'commercial_antivirus_status',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('host_id', sa.UUID(), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=True),
        sa.Column('product_version', sa.String(length=100), nullable=True),
        sa.Column('service_enabled', sa.Boolean(), nullable=True),
        sa.Column('antispyware_enabled', sa.Boolean(), nullable=True),
        sa.Column('antivirus_enabled', sa.Boolean(), nullable=True),
        sa.Column('realtime_protection_enabled', sa.Boolean(), nullable=True),
        sa.Column('full_scan_age', sa.Integer(), nullable=True),
        sa.Column('quick_scan_age', sa.Integer(), nullable=True),
        sa.Column('full_scan_end_time', sa.DateTime(), nullable=True),
        sa.Column('quick_scan_end_time', sa.DateTime(), nullable=True),
        sa.Column('signature_last_updated', sa.DateTime(), nullable=True),
        sa.Column('signature_version', sa.String(length=100), nullable=True),
        sa.Column('tamper_protection_enabled', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_commercial_antivirus_status_host_id'), 'commercial_antivirus_status', ['host_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_commercial_antivirus_status_host_id'), table_name='commercial_antivirus_status')
    op.drop_table('commercial_antivirus_status')
