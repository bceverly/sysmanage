"""Add Linux and Fedora entries to antivirus_default table

Revision ID: h7i8j9k0l1m2
Revises: g6h7i8j9k0l1
Create Date: 2025-12-04 02:55:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# OS names to add with clamav as default
OS_ENTRIES = ["Linux", "Fedora"]


def upgrade() -> None:
    """Add Linux and Fedora entries for antivirus defaults."""
    bind = op.get_bind()

    for os_name in OS_ENTRIES:
        # Check if entry already exists (idempotent)
        result = bind.execute(
            text("SELECT COUNT(*) FROM antivirus_default WHERE os_name = :os_name"),
            {"os_name": os_name},
        )
        count = result.scalar()

        if count == 0:
            # Generate UUID - works for both SQLite and PostgreSQL
            new_uuid = str(uuid4())

            # Insert entry
            bind.execute(
                text(
                    """
                    INSERT INTO antivirus_default (id, os_name, antivirus_package, created_at, updated_at)
                    VALUES (:id, :os_name, 'clamav', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {"id": new_uuid, "os_name": os_name},
            )


def downgrade() -> None:
    """Remove Linux and Fedora entries."""
    bind = op.get_bind()
    for os_name in OS_ENTRIES:
        bind.execute(
            text("DELETE FROM antivirus_default WHERE os_name = :os_name"),
            {"os_name": os_name},
        )
