"""add_antivirus_default_table

Revision ID: eccf2a93022b
Revises: c361ff294476
Create Date: 2025-10-08 09:45:51.948554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eccf2a93022b'
down_revision: Union[str, None] = 'c361ff294476'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'antivirus_default' not in inspector.get_table_names():
        # Create antivirus_default table
        op.create_table(
            'antivirus_default',
            sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('os_name', sa.String(length=100), nullable=False),
            sa.Column('antivirus_package', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('os_name')
        )

        # Create index on os_name for faster lookups
        op.create_index(
            op.f('ix_antivirus_default_os_name'),
            'antivirus_default',
            ['os_name'],
            unique=True
        )


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f('ix_antivirus_default_os_name'), table_name='antivirus_default')

    # Drop table
    op.drop_table('antivirus_default')
