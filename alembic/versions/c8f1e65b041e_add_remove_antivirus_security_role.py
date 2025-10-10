"""add_remove_antivirus_security_role

Revision ID: c8f1e65b041e
Revises: eacc8edaddfc
Create Date: 2025-10-08 10:23:10.758740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f1e65b041e'
down_revision: Union[str, None] = 'eacc8edaddfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add Remove Antivirus role to the Package group
    # Using role ID 48 to continue the sequence
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000048'{uuid_cast}, 'Remove Antivirus', 'Remove antivirus software from hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Remove Antivirus role
    op.execute(f"""
        DELETE FROM security_roles WHERE id = '10000000-0000-0000-0000-000000000048'{uuid_cast}
    """)
