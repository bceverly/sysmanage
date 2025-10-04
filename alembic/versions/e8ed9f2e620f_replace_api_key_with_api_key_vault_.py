"""replace api_key with api_key_vault_token in grafana_integration_settings

Revision ID: e8ed9f2e620f
Revises: ecd0e07d47b2
Create Date: 2025-09-29 12:08:10.771278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8ed9f2e620f'
down_revision: Union[str, None] = 'ecd0e07d47b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if the column exists before attempting to rename it
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the table exists
    tables = inspector.get_table_names()
    if 'grafana_integration_settings' not in tables:
        return  # Table doesn't exist, nothing to do

    # Check if the old column exists and new column doesn't exist
    columns = [col['name'] for col in inspector.get_columns('grafana_integration_settings')]

    if 'api_key' in columns and 'api_key_vault_token' not in columns:
        # Rename api_key column to api_key_vault_token in grafana_integration_settings table
        op.alter_column('grafana_integration_settings', 'api_key', new_column_name='api_key_vault_token')
    elif 'api_key_vault_token' in columns:
        # Column already has the new name, migration already applied
        pass
    elif 'api_key' not in columns and 'api_key_vault_token' not in columns:
        # Neither column exists, add the new one
        op.add_column('grafana_integration_settings', sa.Column('api_key_vault_token', sa.String(255), nullable=True))


def downgrade() -> None:
    # Check if the column exists before attempting to rename it
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the table exists
    tables = inspector.get_table_names()
    if 'grafana_integration_settings' not in tables:
        return  # Table doesn't exist, nothing to do

    # Check if the new column exists and old column doesn't exist
    columns = [col['name'] for col in inspector.get_columns('grafana_integration_settings')]

    if 'api_key_vault_token' in columns and 'api_key' not in columns:
        # Rename api_key_vault_token column back to api_key in grafana_integration_settings table
        op.alter_column('grafana_integration_settings', 'api_key_vault_token', new_column_name='api_key')
    elif 'api_key' in columns:
        # Column already has the old name, downgrade already applied
        pass
