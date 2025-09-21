"""add_missing_update_type_column

Revision ID: 52d6102b1fc1
Revises: b68da58d8a5d
Create Date: 2025-09-21 10:37:51.619040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52d6102b1fc1'
down_revision: Union[str, None] = 'b68da58d8a5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Align package_update table schema with SQLAlchemy model
    from sqlalchemy import inspect
    conn = op.get_bind()

    # Check if we're using SQLite (which doesn't support ALTER COLUMN TYPE)
    if conn.dialect.name == 'sqlite':
        # For SQLite, skip column type changes as they're not supported
        # The test models use Integer anyway for SQLite compatibility
        pass
    else:
        # For PostgreSQL, change id and host_id columns to BigInteger to match model
        op.alter_column('package_update', 'id',
                       existing_type=sa.Integer(),
                       type_=sa.BigInteger(),
                       existing_nullable=False,
                       autoincrement=True)

        op.alter_column('package_update', 'host_id',
                       existing_type=sa.Integer(),
                       type_=sa.BigInteger(),
                       existing_nullable=False)

    # Make current_version NOT NULL to match model
    inspector = inspect(conn)
    existing_columns = {col['name'] for col in inspector.get_columns('package_update')}

    if 'current_version' in existing_columns:
        op.execute("UPDATE package_update SET current_version = '' WHERE current_version IS NULL")

        # SQLite doesn't support ALTER COLUMN ... SET NOT NULL, skip for SQLite
        if conn.dialect.name != 'sqlite':
            op.alter_column('package_update', 'current_version',
                           existing_type=sa.String(length=100),
                           nullable=False)


def downgrade() -> None:
    # Revert changes
    op.alter_column('package_update', 'current_version',
                   existing_type=sa.String(length=100),
                   nullable=True)

    op.alter_column('package_update', 'host_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.Integer(),
                   existing_nullable=False)

    op.alter_column('package_update', 'id',
                   existing_type=sa.BigInteger(),
                   type_=sa.Integer(),
                   existing_nullable=False,
                   autoincrement=True)
