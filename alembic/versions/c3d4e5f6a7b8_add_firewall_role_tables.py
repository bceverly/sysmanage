"""Add firewall role tables and RBAC roles

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-11-26 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from backend.persistence.models.core import GUID

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create firewall_role, firewall_role_open_port, and firewall_role_closed_port tables."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Create firewall_role table
    if "firewall_role" not in tables:
        op.create_table(
            "firewall_role",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column(
                "created_at",
                sa.DateTime,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("created_by", GUID(), nullable=True),
            sa.Column("updated_at", sa.DateTime, nullable=True),
            sa.Column("updated_by", GUID(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["user.id"],
                name="fk_firewall_role_created_by",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["updated_by"],
                ["user.id"],
                name="fk_firewall_role_updated_by",
                ondelete="SET NULL",
            ),
        )
        op.create_index("ix_firewall_role_name", "firewall_role", ["name"])

    # Create firewall_role_open_port table
    if "firewall_role_open_port" not in tables:
        op.create_table(
            "firewall_role_open_port",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("firewall_role_id", GUID(), nullable=False),
            sa.Column("port_number", sa.Integer, nullable=False),
            sa.Column("tcp", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("udp", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["firewall_role_id"],
                ["firewall_role.id"],
                name="fk_open_port_firewall_role",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_firewall_role_open_port_role_id",
            "firewall_role_open_port",
            ["firewall_role_id"],
        )
        op.create_index(
            "ix_firewall_role_open_port_port",
            "firewall_role_open_port",
            ["port_number"],
        )

    # Create firewall_role_closed_port table
    if "firewall_role_closed_port" not in tables:
        op.create_table(
            "firewall_role_closed_port",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("firewall_role_id", GUID(), nullable=False),
            sa.Column("port_number", sa.Integer, nullable=False),
            sa.Column("tcp", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("udp", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["firewall_role_id"],
                ["firewall_role.id"],
                name="fk_closed_port_firewall_role",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_firewall_role_closed_port_role_id",
            "firewall_role_closed_port",
            ["firewall_role_id"],
        )
        op.create_index(
            "ix_firewall_role_closed_port_port",
            "firewall_role_closed_port",
            ["port_number"],
        )

    # Add RBAC roles for Firewall Role Management
    # Using Settings group (00000000-0000-0000-0000-000000000010)
    settings_group_id = "00000000-0000-0000-0000-000000000010"

    # Determine if we're on SQLite or PostgreSQL for UUID casting
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Define the roles to add
    roles_to_add = [
        (
            "10000000-0000-0000-0000-000000000070",
            "Add Firewall Role",
            "Add firewall roles to the system",
        ),
        (
            "10000000-0000-0000-0000-000000000071",
            "Edit Firewall Role",
            "Edit firewall roles in the system",
        ),
        (
            "10000000-0000-0000-0000-000000000072",
            "Delete Firewall Role",
            "Delete firewall roles from the system",
        ),
        (
            "10000000-0000-0000-0000-000000000073",
            "View Firewall Roles",
            "View firewall roles in the system",
        ),
    ]

    # Add each role if it doesn't exist
    for role_id, role_name, role_desc in roles_to_add:
        result = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM security_roles WHERE name = '{role_name}'")
        )
        if result.scalar() == 0:
            op.execute(
                f"""
                INSERT INTO security_roles (id, name, description, group_id)
                VALUES ('{role_id}'{uuid_cast}, '{role_name}', '{role_desc}', '{settings_group_id}'{uuid_cast})
                """
            )


def downgrade() -> None:
    """Drop firewall role tables and RBAC roles."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Remove RBAC roles
    role_names = [
        "Add Firewall Role",
        "Edit Firewall Role",
        "Delete Firewall Role",
        "View Firewall Roles",
    ]
    for role_name in role_names:
        op.execute(f"DELETE FROM security_roles WHERE name = '{role_name}'")

    # Drop tables in reverse order (children first)
    if "firewall_role_closed_port" in tables:
        op.drop_index("ix_firewall_role_closed_port_port", "firewall_role_closed_port")
        op.drop_index(
            "ix_firewall_role_closed_port_role_id", "firewall_role_closed_port"
        )
        op.drop_table("firewall_role_closed_port")

    if "firewall_role_open_port" in tables:
        op.drop_index("ix_firewall_role_open_port_port", "firewall_role_open_port")
        op.drop_index("ix_firewall_role_open_port_role_id", "firewall_role_open_port")
        op.drop_table("firewall_role_open_port")

    if "firewall_role" in tables:
        op.drop_index("ix_firewall_role_name", "firewall_role")
        op.drop_table("firewall_role")
