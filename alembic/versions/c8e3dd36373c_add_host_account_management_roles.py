"""add_host_account_management_roles

Revision ID: c8e3dd36373c
Revises: f6a7b8c9d0e1
Create Date: 2025-11-30 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e3dd36373c"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New security role group for Host Account Management
HOST_ACCOUNT_GROUP_ID = "00000000-0000-0000-0000-000000000010"

# Security roles for host account (user) management
HOST_ACCOUNT_ROLES = [
    (
        "10000000-0000-0000-0000-000000000075",
        "Add Host Account",
        "Create user accounts on remote hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000076",
        "Edit Host Account",
        "Modify user accounts on remote hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000077",
        "Delete Host Account",
        "Remove user accounts from remote hosts",
    ),
]

# Security roles for host group management
HOST_GROUP_ROLES = [
    (
        "10000000-0000-0000-0000-000000000078",
        "Add Host Group",
        "Create groups on remote hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000079",
        "Edit Host Group",
        "Modify groups on remote hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000080",
        "Delete Host Group",
        "Remove groups from remote hosts",
    ),
]


def upgrade() -> None:
    """Add Host Account Management security role group and roles."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Check if group already exists (idempotency)
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

    # Add host account roles
    for role_id, role_name, role_desc in HOST_ACCOUNT_ROLES:
        # Check if role already exists (idempotency)
        result = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM security_roles WHERE name = '{role_name}'")
        )
        role_exists = result.scalar() > 0

        if not role_exists:
            op.execute(
                f"""
                INSERT INTO security_roles (id, name, description, group_id)
                VALUES (
                    '{role_id}'{uuid_cast},
                    '{role_name}',
                    '{role_desc}',
                    '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}
                )
                """
            )

    # Add host group roles
    for role_id, role_name, role_desc in HOST_GROUP_ROLES:
        # Check if role already exists (idempotency)
        result = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM security_roles WHERE name = '{role_name}'")
        )
        role_exists = result.scalar() > 0

        if not role_exists:
            op.execute(
                f"""
                INSERT INTO security_roles (id, name, description, group_id)
                VALUES (
                    '{role_id}'{uuid_cast},
                    '{role_name}',
                    '{role_desc}',
                    '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}
                )
                """
            )


def downgrade() -> None:
    """Remove Host Account Management security roles and group."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove all host account and group roles
    all_role_ids = [role[0] for role in HOST_ACCOUNT_ROLES + HOST_GROUP_ROLES]
    role_ids_str = ", ".join([f"'{rid}'{uuid_cast}" for rid in all_role_ids])

    op.execute(f"DELETE FROM security_roles WHERE id IN ({role_ids_str})")

    # Remove the security role group
    op.execute(
        f"""
        DELETE FROM security_role_groups
        WHERE id = '{HOST_ACCOUNT_GROUP_ID}'{uuid_cast}
        """
    )
