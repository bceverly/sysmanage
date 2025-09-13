"""add_execution_uuid_to_script_execution_log

Revision ID: 43c480c38487
Revises: 7e26542d6fa6
Create Date: 2025-09-12 16:57:28.578989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43c480c38487'
down_revision: Union[str, None] = '7e26542d6fa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add execution_uuid column to script_execution_log table
    op.add_column('script_execution_log',
                  sa.Column('execution_uuid', sa.String(36), nullable=True, unique=True, index=True))

    # Add unique constraint on execution_uuid
    op.create_unique_constraint('uq_script_execution_log_execution_uuid',
                               'script_execution_log', ['execution_uuid'])


def downgrade() -> None:
    # Drop unique constraint
    op.drop_constraint('uq_script_execution_log_execution_uuid', 'script_execution_log')

    # Drop execution_uuid column
    op.drop_column('script_execution_log', 'execution_uuid')
