"""Add host_firewall_role mapping table and RBAC role

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2025-11-28 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create host_firewall_role mapping table and add RBAC role for assigning firewall roles to hosts."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Create host_firewall_role mapping table (many-to-many between host and firewall_role)
    if "host_firewall_role" not in tables:
        op.create_table(
            "host_firewall_role",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("host_id", GUID(), nullable=False),
            sa.Column("firewall_role_id", GUID(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("created_by", GUID(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["host_id"],
                ["host.id"],
                name="fk_host_firewall_role_host",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["firewall_role_id"],
                ["firewall_role.id"],
                name="fk_host_firewall_role_firewall_role",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["user.id"],
                name="fk_host_firewall_role_created_by",
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "host_id", "firewall_role_id", name="uq_host_firewall_role"
            ),
        )
        op.create_index(
            "ix_host_firewall_role_host_id", "host_firewall_role", ["host_id"]
        )
        op.create_index(
            "ix_host_firewall_role_firewall_role_id",
            "host_firewall_role",
            ["firewall_role_id"],
        )

    # Add RBAC role for assigning firewall roles to hosts
    # Using Host Management group (00000000-0000-0000-0000-000000000002)
    host_mgmt_group_id = "00000000-0000-0000-0000-000000000002"

    # Determine if we're on SQLite or PostgreSQL for UUID casting
    is_sqlite = connection.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Check if the role already exists
    result = connection.execute(
        sa.text("SELECT COUNT(*) FROM security_roles WHERE name = 'Assign Host Firewall Roles'")
    )
    if result.scalar() == 0:
        op.execute(
            f"""
            INSERT INTO security_roles (id, name, description, group_id)
            VALUES (
                '10000000-0000-0000-0000-000000000074'{uuid_cast},
                'Assign Host Firewall Roles',
                'Assign firewall roles to hosts',
                '{host_mgmt_group_id}'{uuid_cast}
            )
            """
        )


def downgrade() -> None:
    """Drop host_firewall_role mapping table and remove RBAC role."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Remove RBAC role
    op.execute("DELETE FROM security_roles WHERE name = 'Assign Host Firewall Roles'")

    # Drop the mapping table
    if "host_firewall_role" in tables:
        op.drop_index("ix_host_firewall_role_firewall_role_id", "host_firewall_role")
        op.drop_index("ix_host_firewall_role_host_id", "host_firewall_role")
        op.drop_table("host_firewall_role")
