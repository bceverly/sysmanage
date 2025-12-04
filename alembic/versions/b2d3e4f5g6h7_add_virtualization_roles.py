"""add_virtualization_roles

Revision ID: b2d3e4f5g6h7
Revises: a1c2d3e4f5g6
Create Date: 2025-12-01 10:10:00.000000

This migration adds the Virtualization security role group and
associated roles for managing child hosts (WSL, LXD, VirtualBox, etc.).

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d3e4f5g6h7"
down_revision: Union[str, None] = "a1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New security role group for Virtualization
VIRTUALIZATION_GROUP_ID = "00000000-0000-0000-0000-000000000012"

# Security roles for child host management
VIRTUALIZATION_ROLES = [
    (
        "10000000-0000-0000-0000-000000000081",
        "Create Child Host",
        "Create new virtual machines, containers, or WSL instances",
    ),
    (
        "10000000-0000-0000-0000-000000000082",
        "Delete Child Host",
        "Delete virtual machines, containers, or WSL instances",
    ),
    (
        "10000000-0000-0000-0000-000000000083",
        "Start Child Host",
        "Start a stopped child host",
    ),
    (
        "10000000-0000-0000-0000-000000000084",
        "Stop Child Host",
        "Stop a running child host",
    ),
    (
        "10000000-0000-0000-0000-000000000085",
        "Restart Child Host",
        "Restart a child host",
    ),
    (
        "10000000-0000-0000-0000-000000000086",
        "Configure Child Host",
        "Modify child host settings",
    ),
    (
        "10000000-0000-0000-0000-000000000087",
        "View Child Host",
        "View child host list and details (read-only)",
    ),
]


def upgrade() -> None:
    """Add Virtualization security role group and roles."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Check if group already exists (idempotency)
    result = bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM security_role_groups "
            f"WHERE id = '{VIRTUALIZATION_GROUP_ID}'{uuid_cast}"
        )
    )
    group_exists = result.scalar() > 0

    if not group_exists:
        # Create the Virtualization security role group
        op.execute(
            f"""
            INSERT INTO security_role_groups (id, name, description)
            VALUES (
                '{VIRTUALIZATION_GROUP_ID}'{uuid_cast},
                'Virtualization',
                'Permissions for managing virtual machines, containers, and WSL instances'
            )
            """
        )

    # Add virtualization roles
    for role_id, role_name, role_desc in VIRTUALIZATION_ROLES:
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
                    '{VIRTUALIZATION_GROUP_ID}'{uuid_cast}
                )
                """
            )


def downgrade() -> None:
    """Remove Virtualization security roles and group."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove all virtualization roles
    all_role_ids = [role[0] for role in VIRTUALIZATION_ROLES]
    role_ids_str = ", ".join([f"'{rid}'{uuid_cast}" for rid in all_role_ids])

    op.execute(f"DELETE FROM security_roles WHERE id IN ({role_ids_str})")

    # Remove the security role group
    op.execute(
        f"""
        DELETE FROM security_role_groups
        WHERE id = '{VIRTUALIZATION_GROUP_ID}'{uuid_cast}
        """
    )
