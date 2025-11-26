"""add_enabled_package_manager_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-11-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add enabled_package_manager table and RBAC permissions for managing
    additional package managers per OS.
    """
    # Check if table already exists (idempotent)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "enabled_package_manager" not in tables:
        # Create enabled_package_manager table
        op.create_table(
            "enabled_package_manager",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("os_name", sa.String(100), nullable=False),
            sa.Column("package_manager", sa.String(50), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("created_by", GUID(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
            sa.UniqueConstraint(
                "os_name", "package_manager", name="uq_enabled_pm_os_pm"
            ),
        )

        # Create indexes for efficient lookups
        op.create_index(
            "ix_enabled_package_manager_os_name",
            "enabled_package_manager",
            ["os_name"],
        )
        op.create_index(
            "ix_enabled_package_manager_package_manager",
            "enabled_package_manager",
            ["package_manager"],
        )

    # Add RBAC permissions for enabled package manager management
    # Using Settings group (00000000-0000-0000-0000-000000000010)
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Ensure the Settings role group exists (it should from the default_repository migration)
    settings_group_id = "00000000-0000-0000-0000-000000000010"
    result = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM security_role_groups WHERE id = '{settings_group_id}'")
    )
    group_exists = result.scalar() > 0

    if not group_exists:
        op.execute(
            f"""
            INSERT INTO security_role_groups (id, name, description)
            VALUES ('{settings_group_id}', 'Settings',
                    'Permissions related to system settings and host defaults')
            """
        )

    # Add the enabled package manager management roles (check if they exist first)
    roles_to_add = [
        (
            "10000000-0000-0000-0000-000000000063",
            "Add Enabled Package Manager",
            "Add additional package managers for operating systems",
        ),
        (
            "10000000-0000-0000-0000-000000000064",
            "Remove Enabled Package Manager",
            "Remove additional package managers from operating systems",
        ),
        (
            "10000000-0000-0000-0000-000000000065",
            "View Enabled Package Managers",
            "View the list of enabled additional package managers",
        ),
    ]

    for role_id, role_name, role_desc in roles_to_add:
        # Check if role already exists
        result = bind.execute(
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
    """
    Remove enabled_package_manager table and RBAC permissions.
    """
    # Check if table exists before dropping
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    uuid_cast = "" if is_sqlite else "::uuid"

    # Remove security roles first
    roles_to_delete = [
        "Add Enabled Package Manager",
        "Remove Enabled Package Manager",
        "View Enabled Package Managers",
    ]

    for role_name in roles_to_delete:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )

    if "enabled_package_manager" in tables:
        # Drop indexes first
        op.drop_index(
            "ix_enabled_package_manager_package_manager", "enabled_package_manager"
        )
        op.drop_index("ix_enabled_package_manager_os_name", "enabled_package_manager")

        # Drop table
        op.drop_table("enabled_package_manager")
