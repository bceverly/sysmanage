"""add_enable_bhyve_role

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-01-02 10:00:00.000000

This migration adds the "Enable bhyve" security role for FreeBSD hosts.
bhyve is FreeBSD's native hypervisor, similar to KVM on Linux or VMM on OpenBSD.

The migration is idempotent - it only inserts if the role doesn't exist.
Works on both PostgreSQL and SQLite.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w2x3y4z5a6b7"
down_revision: Union[str, None] = "v1w2x3y4z5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Existing Virtualization security role group
VIRTUALIZATION_GROUP_ID = "00000000-0000-0000-0000-000000000012"

# New security role for bhyve enablement
# Using ID 92 since 88-91 are already used for KVM, LXD, VMM, WSL
BHYVE_ROLE = (
    "10000000-0000-0000-0000-000000000092",
    "Enable bhyve",
    "Enable bhyve virtualization on FreeBSD hosts",
)


def upgrade() -> None:
    """Add Enable bhyve security role."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    role_id, role_name, role_desc = BHYVE_ROLE

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
    """Remove Enable bhyve security role."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    role_id = BHYVE_ROLE[0]
    op.execute(f"DELETE FROM security_roles WHERE id = '{role_id}'{uuid_cast}")
