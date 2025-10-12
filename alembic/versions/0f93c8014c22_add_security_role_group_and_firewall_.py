"""add_security_role_group_and_firewall_roles

Revision ID: 0f93c8014c22
Revises: 8de51f0c3cd3
Create Date: 2025-10-11 07:58:38.169576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f93c8014c22'
down_revision: Union[str, None] = '8de51f0c3cd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add Security role group and firewall management roles.
    Move antivirus roles from Package group to Security group.
    """
    # Create the Security role group with a fixed UUID
    security_group_id = '00000000-0000-0000-0000-000000000009'
    op.execute(
        f"""
        INSERT INTO security_role_groups (id, name, description)
        VALUES ('{security_group_id}', 'Security',
                'Security-related operations including firewall and antivirus management')
        """
    )

    # Add the 4 new firewall roles to the Security group
    firewall_roles = [
        ('Enable Firewall', 'Enable firewall on a host'),
        ('Disable Firewall', 'Disable firewall on a host'),
        ('Edit Firewall Ports', 'Edit open ports in the firewall configuration'),
        ('Restart Firewall', 'Restart the firewall service on a host'),
    ]

    for role_name, role_desc in firewall_roles:
        op.execute(
            f"""
            INSERT INTO security_roles (name, description, group_id)
            VALUES ('{role_name}', '{role_desc}', '{security_group_id}')
            """
        )

    # Move antivirus roles from Package group to Security group
    antivirus_roles = [
        'Enable Antivirus',
        'Disable Antivirus',
        'Manage Antivirus Defaults',
    ]

    for role_name in antivirus_roles:
        op.execute(
            f"""
            UPDATE security_roles
            SET group_id = '{security_group_id}'
            WHERE name = '{role_name}'
            """
        )


def downgrade() -> None:
    """
    Remove Security role group and firewall roles.
    Move antivirus roles back to Package group.
    """
    # Get the Package group ID
    package_group_id = '00000000-0000-0000-0000-000000000002'

    # Move antivirus roles back to Package group
    antivirus_roles = [
        'Enable Antivirus',
        'Disable Antivirus',
        'Manage Antivirus Defaults',
    ]

    for role_name in antivirus_roles:
        op.execute(
            f"""
            UPDATE security_roles
            SET group_id = '{package_group_id}'
            WHERE name = '{role_name}'
            """
        )

    # Delete firewall roles
    firewall_roles = [
        'Enable Firewall',
        'Disable Firewall',
        'Edit Firewall Ports',
        'Restart Firewall',
    ]

    for role_name in firewall_roles:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )

    # Delete the Security role group
    security_group_id = '00000000-0000-0000-0000-000000000009'
    op.execute(
        f"""
        DELETE FROM security_role_groups
        WHERE id = '{security_group_id}'
        """
    )
