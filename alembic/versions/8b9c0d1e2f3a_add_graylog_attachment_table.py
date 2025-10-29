"""add_graylog_attachment_table

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2025-10-21 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = '8b9c0d1e2f3a'
down_revision: Union[str, None] = '7a8b9c0d1e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add graylog_attachment table to track host Graylog connectivity"""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table already exists
    tables = inspector.get_table_names()
    if 'graylog_attachment' not in tables:
        # Create graylog_attachment table
        op.create_table(
            'graylog_attachment',
            sa.Column('id', GUID(), nullable=False),
            sa.Column('host_id', GUID(), nullable=False),
            sa.Column('is_attached', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('target_hostname', sa.String(255), nullable=True),
            sa.Column('target_ip', sa.String(45), nullable=True),  # IPv6 max length
            sa.Column('mechanism', sa.String(50), nullable=True),  # syslog_tcp, syslog_udp, gelf_tcp, windows_sidecar
            sa.Column('port', sa.Integer(), nullable=True),
            sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('host_id', name='uq_graylog_attachment_host_id')  # One record per host
        )


def downgrade() -> None:
    """Remove graylog_attachment table"""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table exists before dropping it
    tables = inspector.get_table_names()
    if 'graylog_attachment' in tables:
        # Drop graylog_attachment table
        op.drop_table('graylog_attachment')
