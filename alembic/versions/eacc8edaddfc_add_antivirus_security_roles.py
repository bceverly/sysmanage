"""add_antivirus_security_roles

Revision ID: eacc8edaddfc
Revises: eccf2a93022b
Create Date: 2025-10-08 09:49:48.785538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eacc8edaddfc'
down_revision: Union[str, None] = 'eccf2a93022b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add Antivirus roles to the Package group
    # Using role IDs 46-47 to continue the sequence (42-45 are already used)
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000046'{uuid_cast}, 'Manage Antivirus Defaults', 'Manage default antivirus software for operating systems', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000047'{uuid_cast}, 'Deploy Antivirus', 'Deploy antivirus software to hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Antivirus roles
    op.execute(f"""
        DELETE FROM security_roles WHERE id IN (
            '10000000-0000-0000-0000-000000000046'{uuid_cast},
            '10000000-0000-0000-0000-000000000047'{uuid_cast}
        )
    """)
