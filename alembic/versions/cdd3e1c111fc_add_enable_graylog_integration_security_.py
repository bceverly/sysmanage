"""add_enable_graylog_integration_security_role

Revision ID: cdd3e1c111fc
Revises: 5deeb1b185e4
Create Date: 2025-10-20 07:16:29.517773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdd3e1c111fc'
down_revision: Union[str, None] = '5deeb1b185e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ENABLE_GRAYLOG_INTEGRATION security role to the Integrations group."""
    # Detect database type for UUID casting
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Check if the role already exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Only insert if security_roles table exists
    tables = inspector.get_table_names()
    if 'security_roles' in tables:
        # Check if the role already exists to make this idempotent
        result = connection.execute(
            sa.text("SELECT COUNT(*) FROM security_roles WHERE name = 'Enable Graylog Integration'")
        )
        count = result.scalar()

        if count == 0:
            # Insert the new security role
            op.execute(f"""
                INSERT INTO security_roles (id, name, description, group_id) VALUES
                ('10000000-0000-0000-0000-000000000051'{uuid_cast},
                 'Enable Graylog Integration',
                 'Enable and configure Graylog integration',
                 '00000000-0000-0000-0000-000000000007'{uuid_cast})
            """)


def downgrade() -> None:
    """Remove ENABLE_GRAYLOG_INTEGRATION security role."""
    # Check if the table exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if 'security_roles' in tables:
        # Delete the role if it exists
        op.execute("""
            DELETE FROM security_roles
            WHERE name = 'Enable Graylog Integration'
        """)
