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
    op.alter_column('secrets', 'key_visibility',
                    new_column_name='secret_subtype')


def downgrade() -> None:
    # Rename secret_subtype column back to key_visibility
    op.alter_column('secrets', 'secret_subtype',
                    new_column_name='key_visibility')
