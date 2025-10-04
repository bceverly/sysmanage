"""add_reset_user_password_role

Revision ID: f62d8480a38c
Revises: 54fcacb0e742
Create Date: 2025-10-03 16:59:29.555910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f62d8480a38c'
down_revision: Union[str, None] = '54fcacb0e742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add the Reset User Password role to the User group
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000036'{uuid_cast}, 'Reset User Password', 'Reset user passwords', '00000000-0000-0000-0000-000000000004'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Reset User Password role
    op.execute(f"""
        DELETE FROM security_roles WHERE id = '10000000-0000-0000-0000-000000000036'{uuid_cast}
    """)
