"""rename key_visibility to secret_subtype

Revision ID: 7c457810ab35
Revises: 712327871c7d
Create Date: 2025-09-24 10:37:30.388095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c457810ab35'
down_revision: Union[str, None] = '712327871c7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename key_visibility column to secret_subtype
    # Check if the old column exists before attempting to rename it
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table('secrets'):
        columns = inspector.get_columns('secrets')
        column_names = [col['name'] for col in columns]

        if 'key_visibility' in column_names:
            # Old column exists, rename it
            op.alter_column('secrets', 'key_visibility',
                           new_column_name='secret_subtype')
        # If key_visibility doesn't exist, assume it's already been renamed or never existed


def downgrade() -> None:
    # Rename secret_subtype column back to key_visibility
    op.alter_column('secrets', 'secret_subtype',
                    new_column_name='key_visibility')
