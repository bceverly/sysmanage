"""add_virtualization_enablement_roles

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
Create Date: 2025-12-31 10:00:00.000000

This migration adds security roles for enabling virtualization platforms:
- Enable WSL (Windows Subsystem for Linux)
- Enable LXD (Linux containers)
- Enable KVM (Kernel-based Virtual Machine)
- Enable VMM (OpenBSD Virtual Machine Monitor)

These roles are separate from the existing child host management roles,
allowing fine-grained control over who can enable virtualization on hosts.

The migration is idempotent - it only inserts if the records don't exist.
Works on both PostgreSQL and SQLite.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t9u0v1w2x3y4"
down_revision: Union[str, None] = "s8t9u0v1w2x3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Existing Virtualization security role group
VIRTUALIZATION_GROUP_ID = "00000000-0000-0000-0000-000000000012"

# New security roles for virtualization enablement (alphabetical by name)
VIRTUALIZATION_ENABLEMENT_ROLES = [
    (
        "10000000-0000-0000-0000-000000000088",
        "Enable KVM",
        "Enable KVM/libvirt virtualization on Linux hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000089",
        "Enable LXD",
        "Enable LXD container support on Linux hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000090",
        "Enable VMM",
        "Enable VMM/vmd virtualization on OpenBSD hosts",
    ),
    (
        "10000000-0000-0000-0000-000000000091",
        "Enable WSL",
        "Enable Windows Subsystem for Linux on Windows hosts",
    ),
]


def upgrade() -> None:
    """Add virtualization enablement security roles."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Add virtualization enablement roles
    for role_id, role_name, role_desc in VIRTUALIZATION_ENABLEMENT_ROLES:
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
    """Remove virtualization enablement security roles."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove all virtualization enablement roles
    all_role_ids = [role[0] for role in VIRTUALIZATION_ENABLEMENT_ROLES]
    role_ids_str = ", ".join([f"'{rid}'{uuid_cast}" for rid in all_role_ids])

    op.execute(f"DELETE FROM security_roles WHERE id IN ({role_ids_str})")
