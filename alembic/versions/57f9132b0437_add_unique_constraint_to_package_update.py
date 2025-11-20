"""add_unique_constraint_to_package_update

Revision ID: 57f9132b0437
Revises: 8b9c0d1e2f3a
Create Date: 2025-11-19 09:47:38.699720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57f9132b0437'
down_revision: Union[str, None] = '8b9c0d1e2f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if we're using SQLite or PostgreSQL
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # Remove duplicate package_update entries
    if dialect_name == 'postgresql':
        # PostgreSQL supports window functions in DELETE
        op.execute("""
            DELETE FROM package_update
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY host_id, package_name, package_manager
                               ORDER BY created_at ASC
                           ) as rn
                    FROM package_update
                ) t
                WHERE t.rn > 1
            )
        """)
    else:
        # SQLite: Use a different approach with temp table
        op.execute("""
            DELETE FROM package_update
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM package_update
                GROUP BY host_id, package_name, package_manager
            )
        """)

    # Add unique constraint on (host_id, package_name, package_manager)
    # Check if constraint already exists to make this idempotent
    from sqlalchemy import inspect
    inspector = inspect(bind)
    constraints = inspector.get_unique_constraints('package_update')
    constraint_names = [c['name'] for c in constraints]

    if 'uq_package_update_host_package_manager' not in constraint_names:
        op.create_unique_constraint(
            'uq_package_update_host_package_manager',
            'package_update',
            ['host_id', 'package_name', 'package_manager']
        )


def downgrade() -> None:
    # Remove the unique constraint
    op.drop_constraint(
        'uq_package_update_host_package_manager',
        'package_update',
        type_='unique'
    )
