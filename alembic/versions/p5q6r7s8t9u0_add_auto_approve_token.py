"""add_auto_approve_token

Revision ID: p5q6r7s8t9u0
Revises: o4p5q6r7s8t9
Create Date: 2025-12-21 10:00:00.000000

This migration adds the auto_approve_token column to the host_child table.
This column stores a UUID that the agent sends back during registration
to enable automatic approval of child hosts created via sysmanage.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "p5q6r7s8t9u0"
down_revision: Union[str, None] = "o4p5q6r7s8t9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add auto_approve_token column to host_child table."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Check if column already exists (idempotent)
    if is_sqlite:
        result = bind.execute(text("PRAGMA table_info(host_child)"))
        columns = [row[1] for row in result]
        if "auto_approve_token" in columns:
            return  # Column already exists
    else:
        result = bind.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'host_child' AND column_name = 'auto_approve_token'
                """
            )
        )
        if result.fetchone() is not None:
            return  # Column already exists

    # Add the column
    op.add_column(
        "host_child",
        sa.Column("auto_approve_token", sa.String(36), nullable=True),
    )

    # Add index for faster lookups during registration
    op.create_index(
        "ix_host_child_auto_approve_token",
        "host_child",
        ["auto_approve_token"],
        unique=False,
    )


def downgrade() -> None:
    """Remove auto_approve_token column from host_child table."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Drop index first
    if is_sqlite:
        # SQLite doesn't support dropping indexes with IF EXISTS in all versions
        try:
            op.drop_index("ix_host_child_auto_approve_token", table_name="host_child")
        except Exception:
            pass  # Index may not exist
    else:
        op.drop_index("ix_host_child_auto_approve_token", table_name="host_child")

    # Drop column
    op.drop_column("host_child", "auto_approve_token")
