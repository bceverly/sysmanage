"""add_deploy_and_remove_firewall_roles

Revision ID: d44688bd27aa
Revises: 85d271dc0e7f
Create Date: 2025-10-11 08:59:20.320997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd44688bd27aa'
down_revision: Union[str, None] = '85d271dc0e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add two new firewall security roles: Deploy Firewall and Remove Firewall.
    """
    import uuid

    # Get the Security group ID
    security_group_id = '00000000-0000-0000-0000-000000000009'

    # Add the 2 new firewall roles with explicit UUIDs
    firewall_roles = [
        ('Deploy Firewall', 'Deploy and configure firewall on a host'),
        ('Remove Firewall', 'Remove firewall from a host'),
    ]

    for role_name, role_desc in firewall_roles:
        role_id = str(uuid.uuid4())
        op.execute(
            f"""
            INSERT INTO security_roles (id, name, description, group_id)
            VALUES ('{role_id}', '{role_name}', '{role_desc}', '{security_group_id}')
            """
        )


def downgrade() -> None:
    """
    Remove the Deploy Firewall and Remove Firewall roles.
    """
    # Delete the roles
    roles_to_delete = [
        'Deploy Firewall',
        'Remove Firewall',
    ]

    for role_name in roles_to_delete:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )
