"""add_view_and_edit_user_security_roles

Revision ID: 85d271dc0e7f
Revises: 0f93c8014c22
Create Date: 2025-10-11 08:15:12.672524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85d271dc0e7f'
down_revision: Union[str, None] = '0f93c8014c22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add two new security roles for managing user security roles.
    """
    # Get the Security group ID
    security_group_id = '00000000-0000-0000-0000-000000000009'

    # Add the 2 new user security role management roles
    user_role_mgmt_roles = [
        ('View User Security Roles',
         'View security roles assigned to users'),
        ('Edit User Security Roles',
         'Edit and manage security roles assigned to users'),
    ]

    for role_name, role_desc in user_role_mgmt_roles:
        op.execute(
            f"""
            INSERT INTO security_roles (name, description, group_id)
            VALUES ('{role_name}', '{role_desc}', '{security_group_id}')
            """
        )


def downgrade() -> None:
    """
    Remove the user security role management roles.
    """
    # Delete the roles
    roles_to_delete = [
        'View User Security Roles',
        'Edit User Security Roles',
    ]

    for role_name in roles_to_delete:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )
