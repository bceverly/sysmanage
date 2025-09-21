"""set_default_operation_type_for_existing_records

Revision ID: fb5228fc17fe
Revises: 7143f0c46db0
Create Date: 2025-09-20 20:38:54.966237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb5228fc17fe'
down_revision: Union[str, None] = '7143f0c46db0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update any existing records that have NULL or empty operation_type to 'install'
    op.execute("""
        UPDATE installation_requests
        SET operation_type = 'install'
        WHERE operation_type IS NULL OR operation_type = ''
    """)


def downgrade() -> None:
    # No downgrade needed - we don't want to remove data that was set
    pass
