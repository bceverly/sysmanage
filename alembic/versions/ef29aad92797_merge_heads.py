"""merge_heads

Revision ID: ef29aad92797
Revises: 9e55362c7c08, add_third_party_repo
Create Date: 2025-10-06 17:06:31.107103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef29aad92797'
down_revision: Union[str, None] = ('9e55362c7c08', 'add_third_party_repo')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
