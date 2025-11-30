"""Add ipv4 and ipv6 columns to firewall_role_open_port table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2025-11-28 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ipv4 and ipv6 boolean columns to firewall_role_open_port table.

    Existing rows will have both ipv4 and ipv6 set to true.
    This migration is idempotent and works on both PostgreSQL and SQLite.
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the table exists
    tables = inspector.get_table_names()
    if "firewall_role_open_port" not in tables:
        return

    # Check which columns already exist
    columns = [col["name"] for col in inspector.get_columns("firewall_role_open_port")]

    # Add ipv4 column if it doesn't exist
    if "ipv4" not in columns:
        op.add_column(
            "firewall_role_open_port",
            sa.Column(
                "ipv4",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1" if connection.dialect.name == "sqlite" else "true"),
            ),
        )

    # Add ipv6 column if it doesn't exist
    if "ipv6" not in columns:
        op.add_column(
            "firewall_role_open_port",
            sa.Column(
                "ipv6",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1" if connection.dialect.name == "sqlite" else "true"),
            ),
        )


def downgrade() -> None:
    """Remove ipv4 and ipv6 columns from firewall_role_open_port table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check if the table exists
    tables = inspector.get_table_names()
    if "firewall_role_open_port" not in tables:
        return

    # Check which columns exist
    columns = [col["name"] for col in inspector.get_columns("firewall_role_open_port")]

    if "ipv6" in columns:
        op.drop_column("firewall_role_open_port", "ipv6")

    if "ipv4" in columns:
        op.drop_column("firewall_role_open_port", "ipv4")
