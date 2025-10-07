"""add_enable_disable_third_party_repository_roles

Revision ID: c361ff294476
Revises: ef29aad92797
Create Date: 2025-10-06 17:06:44.318633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c361ff294476'
down_revision: Union[str, None] = 'ef29aad92797'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add Enable/Disable Third-Party Repository roles to the Package group
    # Using role IDs 44-45 to continue the sequence
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000044'{uuid_cast}, 'Enable Third-Party Repository', 'Enable third-party repositories on hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000045'{uuid_cast}, 'Disable Third-Party Repository', 'Disable third-party repositories on hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the Enable/Disable Third-Party Repository roles
    op.execute(f"""
        DELETE FROM security_roles WHERE id IN (
            '10000000-0000-0000-0000-000000000044'{uuid_cast},
            '10000000-0000-0000-0000-000000000045'{uuid_cast}
        )
    """)
