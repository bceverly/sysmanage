"""add_graylog_input_ports_tracking

Revision ID: 7a8b9c0d1e2f
Revises: 6f3a4b2e8c1d
Create Date: 2025-10-20 19:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '7a8b9c0d1e2f'
down_revision: Union[str, None] = '6f3a4b2e8c1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add columns to track detected Graylog input ports"""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table exists
    tables = inspector.get_table_names()
    if 'graylog_integration_settings' not in tables:
        # Table doesn't exist, skip migration
        return

    # Get existing columns
    existing_columns = [col['name'] for col in inspector.get_columns('graylog_integration_settings')]

    # Add columns if they don't exist
    if 'has_gelf_tcp' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('has_gelf_tcp', sa.Boolean(), nullable=True))

    if 'gelf_tcp_port' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('gelf_tcp_port', sa.Integer(), nullable=True))

    if 'has_syslog_tcp' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('has_syslog_tcp', sa.Boolean(), nullable=True))

    if 'syslog_tcp_port' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('syslog_tcp_port', sa.Integer(), nullable=True))

    if 'has_syslog_udp' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('has_syslog_udp', sa.Boolean(), nullable=True))

    if 'syslog_udp_port' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('syslog_udp_port', sa.Integer(), nullable=True))

    if 'has_windows_sidecar' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('has_windows_sidecar', sa.Boolean(), nullable=True))

    if 'windows_sidecar_port' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('windows_sidecar_port', sa.Integer(), nullable=True))

    if 'inputs_last_checked' not in existing_columns:
        op.add_column('graylog_integration_settings',
                      sa.Column('inputs_last_checked', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove Graylog input ports tracking columns"""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if table exists
    tables = inspector.get_table_names()
    if 'graylog_integration_settings' not in tables:
        # Table doesn't exist, skip migration
        return

    # Get existing columns
    existing_columns = [col['name'] for col in inspector.get_columns('graylog_integration_settings')]

    # Drop columns if they exist
    if 'inputs_last_checked' in existing_columns:
        op.drop_column('graylog_integration_settings', 'inputs_last_checked')

    if 'windows_sidecar_port' in existing_columns:
        op.drop_column('graylog_integration_settings', 'windows_sidecar_port')

    if 'has_windows_sidecar' in existing_columns:
        op.drop_column('graylog_integration_settings', 'has_windows_sidecar')

    if 'syslog_udp_port' in existing_columns:
        op.drop_column('graylog_integration_settings', 'syslog_udp_port')

    if 'has_syslog_udp' in existing_columns:
        op.drop_column('graylog_integration_settings', 'has_syslog_udp')

    if 'syslog_tcp_port' in existing_columns:
        op.drop_column('graylog_integration_settings', 'syslog_tcp_port')

    if 'has_syslog_tcp' in existing_columns:
        op.drop_column('graylog_integration_settings', 'has_syslog_tcp')

    if 'gelf_tcp_port' in existing_columns:
        op.drop_column('graylog_integration_settings', 'gelf_tcp_port')

    if 'has_gelf_tcp' in existing_columns:
        op.drop_column('graylog_integration_settings', 'has_gelf_tcp')
