"""Add reboot_required_reason column to host table

Revision ID: e5f6g7h8i9j0
Revises: d4f5g6h7i8j9
Create Date: 2024-12-02 16:40:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5f6g7h8i9j0"
down_revision = "d4f5g6h7i8j9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add reboot_required_reason column to host table (idempotent)."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the host table exists
    tables = inspector.get_table_names()
    if "host" not in tables:
        return

    # Get existing columns
    columns = [col["name"] for col in inspector.get_columns("host")]

    # Add reboot_required_reason column if it doesn't exist
    if "reboot_required_reason" not in columns:
        op.add_column(
            "host",
            sa.Column("reboot_required_reason", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    """Remove reboot_required_reason column from host table (idempotent)."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the host table exists
    tables = inspector.get_table_names()
    if "host" not in tables:
        return

    # Get existing columns
    columns = [col["name"] for col in inspector.get_columns("host")]

    # Drop column if it exists
    if "reboot_required_reason" in columns:
        op.drop_column("host", "reboot_required_reason")
