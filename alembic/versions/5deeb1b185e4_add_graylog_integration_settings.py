"""add_graylog_integration_settings

Revision ID: 5deeb1b185e4
Revises: 95d0a56a3255
Create Date: 2025-10-19 20:30:45.551541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = '5deeb1b185e4'
down_revision: Union[str, None] = '95d0a56a3255'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if graylog_integration_settings table already exists before creating it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'graylog_integration_settings' not in tables:
        # Create graylog_integration_settings table
        op.create_table(
            'graylog_integration_settings',
            sa.Column('id', GUID(), nullable=False),
            sa.Column('enabled', sa.Boolean(), default=False, nullable=False),
            sa.Column('host_id', GUID(), nullable=True),  # References host.id when using managed server
            sa.Column('manual_url', sa.String(255), nullable=True),  # Manual URL when not using managed server
            sa.Column('use_managed_server', sa.Boolean(), default=True, nullable=False),  # True for dropdown, False for manual
            sa.Column('api_token_vault_token', sa.String(255), nullable=True),  # Vault token for Graylog API token
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='SET NULL'),
        )


def downgrade() -> None:
    # Check if graylog_integration_settings table exists before dropping it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'graylog_integration_settings' in tables:
        # Drop graylog_integration_settings table
        op.drop_table('graylog_integration_settings')
