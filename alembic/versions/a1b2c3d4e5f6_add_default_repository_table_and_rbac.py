"""add_default_repository_table_and_rbac

Revision ID: a1b2c3d4e5f6
Revises: e116a9596f20
Create Date: 2025-11-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from backend.persistence.models.core import GUID


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e116a9596f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add default_repository table and RBAC permissions for managing default repositories.
    """
    # Check if table already exists (idempotent)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'default_repository' not in tables:
        # Create default_repository table
        op.create_table(
            'default_repository',
            sa.Column('id', GUID(), nullable=False),
            sa.Column('os_name', sa.String(100), nullable=False),
            sa.Column('package_manager', sa.String(50), nullable=False),
            sa.Column('repository_url', sa.String(1000), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('created_by', GUID(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        )

        # Create indexes for efficient lookups
        op.create_index('ix_default_repository_os_name', 'default_repository', ['os_name'])
        op.create_index('ix_default_repository_package_manager', 'default_repository', ['package_manager'])
        op.create_index('ix_default_repository_os_pm', 'default_repository', ['os_name', 'package_manager'])

    # Add RBAC permissions for default repository management
    # Using Settings group (00000000-0000-0000-0000-000000000010) - need to create it first
    # Or use Integrations group (00000000-0000-0000-0000-000000000007) since this is a settings/config feature
    # Let's create a new "Settings" group for this

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Create the Settings role group with a fixed UUID (check if exists first)
    settings_group_id = '00000000-0000-0000-0000-000000000010'
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

    # Add the default repository management roles (check if they exist first)
    roles_to_add = [
        ('10000000-0000-0000-0000-000000000060', 'Add Default Repository',
         'Add default repositories that will be applied to new hosts'),
        ('10000000-0000-0000-0000-000000000061', 'Remove Default Repository',
         'Remove default repositories from the system'),
        ('10000000-0000-0000-0000-000000000062', 'View Default Repositories',
         'View the list of default repositories'),
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
    Remove default_repository table and RBAC permissions.
    """
    # Check if table exists before dropping
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    # Remove security roles first
    roles_to_delete = [
        'Add Default Repository',
        'Remove Default Repository',
        'View Default Repositories',
    ]

    for role_name in roles_to_delete:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )

    # Remove the Settings security role group if it has no other roles
    bind = op.get_bind()
    settings_group_id = '00000000-0000-0000-0000-000000000010'
    result = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM security_roles WHERE group_id = '{settings_group_id}'")
    )
    if result.scalar() == 0:
        op.execute(
            f"""
            DELETE FROM security_role_groups
            WHERE id = '{settings_group_id}'
            """
        )

    if 'default_repository' in tables:
        # Drop indexes first
        op.drop_index('ix_default_repository_os_pm', 'default_repository')
        op.drop_index('ix_default_repository_package_manager', 'default_repository')
        op.drop_index('ix_default_repository_os_name', 'default_repository')

        # Drop table
        op.drop_table('default_repository')
