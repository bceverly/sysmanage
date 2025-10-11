"""fix_commercial_antivirus_scan_age_overflow

Revision ID: f9c0314521b9
Revises: 7ee1f0bd6b87
Create Date: 2025-10-10 16:24:17.242504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9c0314521b9'
down_revision: Union[str, None] = '7ee1f0bd6b87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change full_scan_age and quick_scan_age from INTEGER to BIGINT
    # This fixes overflow with Windows Defender's 4294967295 (2^32-1) for "never scanned"
    op.alter_column(
        'commercial_antivirus_status',
        'full_scan_age',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )
    op.alter_column(
        'commercial_antivirus_status',
        'quick_scan_age',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True
    )


def downgrade() -> None:
    # Revert back to INTEGER (may lose data if values exceed INTEGER range)
    op.alter_column(
        'commercial_antivirus_status',
        'quick_scan_age',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True
    )
    op.alter_column(
        'commercial_antivirus_status',
        'full_scan_age',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True
    )
