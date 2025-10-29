"""Add Connect Host to Graylog security role

Revision ID: 6f3a4b2e8c1d
Revises: cdd3e1c111fc
Create Date: 2025-10-20 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '6f3a4b2e8c1d'
down_revision = 'cdd3e1c111fc'
branch_labels = None
depends_on = None

# UUID for the new security role
CONNECT_HOST_TO_GRAYLOG_ROLE_ID = 'ab6fd7ba-0bc5-4350-864c-4cf875c08f7f'


def upgrade() -> None:
    """Add Connect Host to Graylog security role"""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if we're using PostgreSQL or SQLite
    is_postgresql = bind.dialect.name == 'postgresql'

    # Insert the new security role (idempotent - only if it doesn't exist)
    # Use the same group_id as other integration roles (00000000-0000-0000-0000-000000000007)
    INTEGRATION_GROUP_ID = '00000000-0000-0000-0000-000000000007'

    if is_postgresql:
        # PostgreSQL - use UUID type
        op.execute(
            """
            INSERT INTO security_roles (id, name, description, group_id)
            SELECT '%s'::uuid, 'Connect Host to Graylog', 'Permission to attach hosts to Graylog for log aggregation', '%s'::uuid
            WHERE NOT EXISTS (
                SELECT 1 FROM security_roles WHERE id = '%s'::uuid
            );
            """ % (CONNECT_HOST_TO_GRAYLOG_ROLE_ID, INTEGRATION_GROUP_ID, CONNECT_HOST_TO_GRAYLOG_ROLE_ID)
        )
    else:
        # SQLite - use string for UUID
        op.execute(
            """
            INSERT INTO security_roles (id, name, description, group_id)
            SELECT '%s', 'Connect Host to Graylog', 'Permission to attach hosts to Graylog for log aggregation', '%s'
            WHERE NOT EXISTS (
                SELECT 1 FROM security_roles WHERE id = '%s'
            );
            """ % (CONNECT_HOST_TO_GRAYLOG_ROLE_ID, INTEGRATION_GROUP_ID, CONNECT_HOST_TO_GRAYLOG_ROLE_ID)
        )


def downgrade() -> None:
    """Remove Connect Host to Graylog security role"""
    bind = op.get_bind()

    # Check if we're using PostgreSQL or SQLite
    is_postgresql = bind.dialect.name == 'postgresql'

    # Remove the security role
    if is_postgresql:
        op.execute(
            """
            DELETE FROM security_roles WHERE id = '%s'::uuid;
            """ % CONNECT_HOST_TO_GRAYLOG_ROLE_ID
        )
    else:
        op.execute(
            """
            DELETE FROM security_roles WHERE id = '%s';
            """ % CONNECT_HOST_TO_GRAYLOG_ROLE_ID
        )
