"""fix_host_account_management_group

Revision ID: 826d330052cc
Revises: c8e3dd36373c
Create Date: 2025-11-30 12:30:00.000000

This migration fixes the Host Account Management security role group.
The previous migration incorrectly used group ID 10 which was already
taken by the Settings group. This migration:
1. Creates the proper Host Account Management group with ID 11
2. Updates the host account roles to point to the correct group

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "826d330052cc"
down_revision: Union[str, None] = "c8e3dd36373c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Correct security role group ID for Host Account Management
HOST_ACCOUNT_GROUP_ID = "00000000-0000-0000-0000-000000000011"

# The old incorrect group ID (Settings)
OLD_GROUP_ID = "00000000-0000-0000-0000-000000000010"

# Role IDs that need to be updated
HOST_ACCOUNT_ROLE_IDS = [
    "10000000-0000-0000-0000-000000000075",
    "10000000-0000-0000-0000-000000000076",
    "10000000-0000-0000-0000-000000000077",
    "10000000-0000-0000-0000-000000000078",
    "10000000-0000-0000-0000-000000000079",
    "10000000-0000-0000-0000-000000000080",
]


def upgrade() -> None:
    """Create Host Account Management group and update roles."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Check if the correct group already exists (idempotency)
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM security_role_groups "
            f"WHERE id = '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}"
        )
    )
    group_exists = result.scalar() > 0

    if not group_exists:
        # Create the Host Account Management security role group
        op.execute(
            f"""
            INSERT INTO security_role_groups (id, name, description)
            VALUES (
                '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast},
                'Host Account Management',
                'Permissions for managing user accounts and groups on remote hosts'
            )
            """
        )

    # Update the roles to point to the correct group
    role_ids_str = ", ".join([f"'{rid}'{uuid_cast}" for rid in HOST_ACCOUNT_ROLE_IDS])
    op.execute(
        f"""
        UPDATE security_roles
        SET group_id = '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}
        WHERE id IN ({role_ids_str})
        """
    )


def downgrade() -> None:
    """Revert roles to old group and remove new group."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Move roles back to the Settings group
    role_ids_str = ", ".join([f"'{rid}'{uuid_cast}" for rid in HOST_ACCOUNT_ROLE_IDS])
    op.execute(
        f"""
        UPDATE security_roles
        SET group_id = '{OLD_GROUP_ID}'{uuid_cast}
        WHERE id IN ({role_ids_str})
        """
    )

    # Remove the Host Account Management security role group
    op.execute(
        f"""
        DELETE FROM security_role_groups
        WHERE id = '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}
        """
    )
