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
    # Rename api_key column to api_key_vault_token in grafana_integration_settings table
    op.alter_column('grafana_integration_settings', 'api_key', new_column_name='api_key_vault_token')


def downgrade() -> None:
    # Rename api_key_vault_token column back to api_key in grafana_integration_settings table
    op.alter_column('grafana_integration_settings', 'api_key_vault_token', new_column_name='api_key')
