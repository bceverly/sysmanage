"""add_edit_host_hostname_role

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2025-01-30 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Add the Edit Host Hostname role to the Host Management group
    # Host Management group ID: 00000000-0000-0000-0000-000000000002
    # Next available role ID: 10000000-0000-0000-0000-000000000093
    op.execute(
        f"""
        INSERT INTO security_roles (id, name, description, group_id)
        SELECT
            '10000000-0000-0000-0000-000000000093'{uuid_cast},
            'Edit Host Hostname',
            'Change the hostname of managed hosts',
            '00000000-0000-0000-0000-000000000002'{uuid_cast}
        WHERE NOT EXISTS (
            SELECT 1 FROM security_roles
            WHERE id = '10000000-0000-0000-0000-000000000093'{uuid_cast}
        )
    """
    )


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove the Edit Host Hostname role
    op.execute(
        f"""
        DELETE FROM security_roles
        WHERE id = '10000000-0000-0000-0000-000000000093'{uuid_cast}
    """
    )
