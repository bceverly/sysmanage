"""add_grafana_integration_settings

Revision ID: ecd0e07d47b2
Revises: f02c3958456f
Create Date: 2025-09-29 10:41:34.297499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = 'ecd0e07d47b2'
down_revision: Union[str, None] = 'f02c3958456f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create grafana_integration_settings table
    op.create_table(
        'grafana_integration_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), default=False, nullable=False),
        sa.Column('host_id', GUID(), nullable=True),  # References host.id when using managed server
        sa.Column('manual_url', sa.String(255), nullable=True),  # Manual URL when not using managed server
        sa.Column('use_managed_server', sa.Boolean(), default=True, nullable=False),  # True for dropdown, False for manual
        sa.Column('api_key', sa.String(255), nullable=True),  # Optional Grafana API key for enhanced features
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='SET NULL'),
    )


def downgrade() -> None:
    # Drop grafana_integration_settings table
    op.drop_table('grafana_integration_settings')
