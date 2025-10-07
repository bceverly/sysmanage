"""add_third_party_repository_table

Revision ID: add_third_party_repo
Revises: ed9659130b39
Create Date: 2025-10-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = 'add_third_party_repo'
down_revision: Union[str, None] = 'ed9659130b39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if third_party_repository table already exists before creating it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'third_party_repository' not in tables:
        # Create third_party_repository table
        op.create_table(
            'third_party_repository',
            sa.Column('id', GUID(), nullable=False),
            sa.Column('host_id', GUID(), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('type', sa.String(50), nullable=False),
            sa.Column('url', sa.String(500), nullable=True),
            sa.Column('enabled', sa.Boolean(), nullable=False, default=True),
            sa.Column('file_path', sa.String(500), nullable=True),
            sa.Column('last_updated', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        )

        # Create index on host_id for efficient lookups
        op.create_index('ix_third_party_repository_host_id', 'third_party_repository', ['host_id'])


def downgrade() -> None:
    # Check if third_party_repository table exists before dropping it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'third_party_repository' in tables:
        # Drop index first
        op.drop_index('ix_third_party_repository_host_id', 'third_party_repository')

        # Drop third_party_repository table
        op.drop_table('third_party_repository')
