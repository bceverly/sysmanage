"""Add parent_host_id column to host table for child host relationships

Revision ID: i8j9k0l1m2n3
Revises: h7i8j9k0l1m2
Create Date: 2025-12-04 03:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parent_host_id column to host table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if column already exists (idempotent)
    columns = [col["name"] for col in inspector.get_columns("host")]
    if "parent_host_id" not in columns:
        # Add nullable foreign key column
        # Using String type for UUID compatibility with both SQLite and PostgreSQL
        op.add_column(
            "host",
            sa.Column("parent_host_id", sa.String(36), nullable=True),
        )

        # Add index for faster parent/child lookups
        op.create_index(
            "ix_host_parent_host_id",
            "host",
            ["parent_host_id"],
        )

        # Note: We don't add a foreign key constraint here because:
        # 1. SQLite has limited FK support
        # 2. The application logic already handles the relationship
        # 3. It allows for more flexibility (e.g., orphaned child hosts)


def downgrade() -> None:
    """Remove parent_host_id column from host table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if index exists before dropping
    indexes = [idx["name"] for idx in inspector.get_indexes("host")]
    if "ix_host_parent_host_id" in indexes:
        op.drop_index("ix_host_parent_host_id", table_name="host")

    # Check if column exists before dropping
    columns = [col["name"] for col in inspector.get_columns("host")]
    if "parent_host_id" in columns:
        op.drop_column("host", "parent_host_id")
