"""expand key_visibility column for ssl certificates

Revision ID: 712327871c7d
Revises: 392b0f4105cf
Create Date: 2025-09-24 09:24:02.155617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '712327871c7d'
down_revision: Union[str, None] = '392b0f4105cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expand key_visibility column to support SSL certificate subtypes
    # Check if the table exists and column needs to be expanded
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table('secrets'):
        # Check current column size and only alter if it's currently String(20)
        columns = inspector.get_columns('secrets')
        key_vis_column = next((col for col in columns if col['name'] == 'key_visibility'), None)

        # Only alter if the column exists and needs expansion
        if key_vis_column and hasattr(key_vis_column['type'], 'length') and key_vis_column['type'].length == 20:
            op.alter_column('secrets', 'key_visibility',
                           type_=sa.String(30),
                           existing_type=sa.String(20))


def downgrade() -> None:
    # Revert key_visibility column back to original size
    op.alter_column('secrets', 'key_visibility',
                   type_=sa.String(20),
                   existing_type=sa.String(30))
