"""add_third_party_repository_roles

Revision ID: 9e55362c7c08
Revises: 74b6aab99736
Create Date: 2025-10-06 15:10:54.103659

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e55362c7c08'
down_revision: Union[str, None] = '74b6aab99736'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add Third-Party Repository roles to the Package group
    # Using role IDs 42-43 to continue the sequence
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000042'{uuid_cast}, 'Add Third-Party Repository', 'Add third-party repositories to hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000043'{uuid_cast}, 'Delete Third-Party Repository', 'Delete third-party repositories from hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Third-Party Repository roles
    op.execute(f"""
        DELETE FROM security_roles WHERE id IN (
            '10000000-0000-0000-0000-000000000042'{uuid_cast},
            '10000000-0000-0000-0000-000000000043'{uuid_cast}
        )
    """)
