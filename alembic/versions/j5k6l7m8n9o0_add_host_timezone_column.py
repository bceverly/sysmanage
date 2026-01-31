"""add_host_timezone_column

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2025-01-30 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add timezone column to host table
    # Check if column already exists (idempotent for both SQLite and PostgreSQL)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("host")]

    if "timezone" not in columns:
        op.add_column("host", sa.Column("timezone", sa.String(100), nullable=True))


def downgrade() -> None:
    # Remove timezone column from host table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("host")]

    if "timezone" in columns:
        op.drop_column("host", "timezone")
