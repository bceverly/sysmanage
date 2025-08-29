"""Add certificate fields to host table

Revision ID: 995799008308
Revises: 4dc3b0afdff6
Create Date: 2025-08-29 09:26:57.972113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '995799008308'
down_revision: Union[str, None] = '4dc3b0afdff6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add certificate-related columns to host table
    op.add_column('host', sa.Column('client_certificate', sa.Text(), nullable=True))
    op.add_column('host', sa.Column('certificate_serial', sa.String(length=64), nullable=True))
    op.add_column('host', sa.Column('certificate_issued_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove certificate-related columns from host table
    op.drop_column('host', 'certificate_issued_at')
    op.drop_column('host', 'certificate_serial')
    op.drop_column('host', 'client_certificate')
