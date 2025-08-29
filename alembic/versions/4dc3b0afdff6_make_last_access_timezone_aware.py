"""Make last_access timezone aware

Revision ID: 4dc3b0afdff6
Revises: a7df4f0c61d9
Create Date: 2025-08-29 08:45:20.299555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4dc3b0afdff6'
down_revision: Union[str, None] = 'a7df4f0c61d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert last_access columns to timezone-aware for both host and user tables
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        # SQLite doesn't distinguish between timezone-aware and naive DateTime
        # Skip this migration for SQLite
        pass
    else:
        # PostgreSQL and other databases
        op.alter_column('host', 'last_access', type_=sa.DateTime(timezone=True))
        op.alter_column('user', 'last_access', type_=sa.DateTime(timezone=True))


def downgrade() -> None:
    # Revert last_access columns to timezone-naive
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        # SQLite doesn't distinguish between timezone-aware and naive DateTime
        # Skip this migration for SQLite
        pass
    else:
        # PostgreSQL and other databases
        op.alter_column('host', 'last_access', type_=sa.DateTime())
        op.alter_column('user', 'last_access', type_=sa.DateTime())
