"""Add reboot_required fields to host table

Revision ID: 94ceb33566ec
Revises: 32f8ccabde5a
Create Date: 2025-09-08 12:36:52.451053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94ceb33566ec'
down_revision: Union[str, None] = '32f8ccabde5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reboot_required field to host table
    op.add_column('host', sa.Column('reboot_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('host', sa.Column('reboot_required_updated_at', sa.DateTime(timezone=True), nullable=True))

    # Add index for reboot_required field
    op.create_index('ix_host_reboot_required', 'host', ['reboot_required'])


def downgrade() -> None:
    # Remove index and columns
    op.drop_index('ix_host_reboot_required', table_name='host')
    op.drop_column('host', 'reboot_required_updated_at')
    op.drop_column('host', 'reboot_required')
