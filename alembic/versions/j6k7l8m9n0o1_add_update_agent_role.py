"""add_update_agent_role

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2026-02-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "j6k7l8m9n0o1"
down_revision: Union[str, None] = "i5j6k7l8m9n0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Add the Update Agent role to the Host Management group
    # Host Management group ID: 00000000-0000-0000-0000-000000000002
    # Next available role ID: 10000000-0000-0000-0000-000000000094
    op.execute(
        f"""
        INSERT INTO security_roles (id, name, description, group_id)
        SELECT
            '10000000-0000-0000-0000-000000000094'{uuid_cast},
            'Update Agent',
            'Update the sysmanage-agent on managed hosts',
            '00000000-0000-0000-0000-000000000002'{uuid_cast}
        WHERE NOT EXISTS (
            SELECT 1 FROM security_roles
            WHERE id = '10000000-0000-0000-0000-000000000094'{uuid_cast}
        )
    """
    )


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove the Update Agent role
    op.execute(
        f"""
        DELETE FROM security_roles
        WHERE id = '10000000-0000-0000-0000-000000000094'{uuid_cast}
    """
    )
