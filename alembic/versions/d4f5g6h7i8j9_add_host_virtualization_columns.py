"""Add host virtualization columns

Revision ID: d4f5g6h7i8j9
Revises: c3e4f5g6h7i8
Create Date: 2024-12-02 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4f5g6h7i8j9"
down_revision = "c3e4f5g6h7i8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add virtualization capability columns to host table (idempotent)."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the host table exists
    tables = inspector.get_table_names()
    if "host" not in tables:
        return

    # Get existing columns
    columns = [col["name"] for col in inspector.get_columns("host")]

    # Add virtualization_types column if it doesn't exist
    if "virtualization_types" not in columns:
        op.add_column(
            "host",
            sa.Column("virtualization_types", sa.Text(), nullable=True),
        )

    # Add virtualization_capabilities column if it doesn't exist
    if "virtualization_capabilities" not in columns:
        op.add_column(
            "host",
            sa.Column("virtualization_capabilities", sa.Text(), nullable=True),
        )

    # Add virtualization_updated_at column if it doesn't exist
    if "virtualization_updated_at" not in columns:
        op.add_column(
            "host",
            sa.Column("virtualization_updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    """Remove virtualization capability columns from host table (idempotent)."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the host table exists
    tables = inspector.get_table_names()
    if "host" not in tables:
        return

    # Get existing columns
    columns = [col["name"] for col in inspector.get_columns("host")]

    # Drop columns if they exist
    if "virtualization_updated_at" in columns:
        op.drop_column("host", "virtualization_updated_at")
    if "virtualization_capabilities" in columns:
        op.drop_column("host", "virtualization_capabilities")
    if "virtualization_types" in columns:
        op.drop_column("host", "virtualization_types")
