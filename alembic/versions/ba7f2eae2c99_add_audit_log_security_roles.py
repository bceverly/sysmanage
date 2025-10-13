"""add_audit_log_security_roles

Revision ID: ba7f2eae2c99
Revises: 10ed1b8b7511
Create Date: 2025-10-12 19:23:20.919015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba7f2eae2c99'
down_revision: Union[str, None] = '10ed1b8b7511'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add security roles for audit log management.
    """
    import uuid

    # Get the Security group ID
    security_group_id = '00000000-0000-0000-0000-000000000009'

    # Add the audit log management roles with explicit UUIDs
    audit_log_roles = [
        ('View Audit Log',
         'View audit log entries to track system changes and user actions'),
        ('Export Audit Log',
         'Export audit log data to PDF and other formats'),
    ]

    for role_name, role_desc in audit_log_roles:
        role_id = str(uuid.uuid4())
        op.execute(
            f"""
            INSERT INTO security_roles (id, name, description, group_id)
            VALUES ('{role_id}', '{role_name}', '{role_desc}', '{security_group_id}')
            """
        )


def downgrade() -> None:
    """
    Remove the audit log management roles.
    """
    # Delete the roles
    roles_to_delete = [
        'View Audit Log',
        'Export Audit Log',
    ]

    for role_name in roles_to_delete:
        op.execute(
            f"""
            DELETE FROM security_roles
            WHERE name = '{role_name}'
            """
        )
