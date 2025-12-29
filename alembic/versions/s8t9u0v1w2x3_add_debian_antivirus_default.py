"""add_debian_antivirus_default

Revision ID: s8t9u0v1w2x3
Revises: r7s8t9u0v1w2
Create Date: 2025-12-26 19:30:00.000000

This migration adds Debian to the antivirus_default table with clamav
as the default antivirus package.

The migration is idempotent - it only inserts if the record doesn't exist.
Works on both PostgreSQL and SQLite.
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "s8t9u0v1w2x3"
down_revision: Union[str, None] = "r7s8t9u0v1w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Debian to antivirus_default table if not exists."""
    conn = op.get_bind()

    # Check if Debian already exists
    result = conn.execute(
        text("SELECT COUNT(*) FROM antivirus_default WHERE os_name = 'Debian'")
    )
    count = result.scalar()

    if count == 0:
        # Generate UUID and timestamp
        new_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        # Insert Debian with clamav as default
        conn.execute(
            text(
                """
                INSERT INTO antivirus_default (id, os_name, antivirus_package, created_at, updated_at)
                VALUES (:id, :os_name, :antivirus_package, :created_at, :updated_at)
                """
            ),
            {
                "id": new_id,
                "os_name": "Debian",
                "antivirus_package": "clamav",
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    """Remove Debian from antivirus_default table if exists."""
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM antivirus_default WHERE os_name = 'Debian'")
    )
