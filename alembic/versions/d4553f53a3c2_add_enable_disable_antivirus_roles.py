"""add enable and disable antivirus roles

Revision ID: d4553f53a3c2
Revises: 9cf6fe668c7e
Create Date: 2025-10-08 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4553f53a3c2'
down_revision: Union[str, None] = '9cf6fe668c7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Enable Antivirus and Disable Antivirus security roles."""
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add Enable and Disable Antivirus roles to the Package group
    # Using role IDs 49-50 to continue the sequence (46-48 are already used)
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000049'{uuid_cast}, 'Enable Antivirus', 'Enable antivirus software on hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000050'{uuid_cast}, 'Disable Antivirus', 'Disable antivirus software on hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast})
    """)


def downgrade() -> None:
    """Remove Enable Antivirus and Disable Antivirus security roles."""
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Enable and Disable Antivirus roles
    op.execute(f"""
        DELETE FROM security_roles WHERE id IN (
            '10000000-0000-0000-0000-000000000049'{uuid_cast},
            '10000000-0000-0000-0000-000000000050'{uuid_cast}
        )
    """)
