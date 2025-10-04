"""add_edit_script_role

Revision ID: ed9659130b39
Revises: f62d8480a38c
Create Date: 2025-10-03 17:14:39.076835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed9659130b39'
down_revision: Union[str, None] = 'f62d8480a38c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the Edit Script role to the Scripts group
    op.execute("""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000037'::uuid, 'Edit Script', 'Edit existing scripts', '00000000-0000-0000-0000-000000000005'::uuid)
    """)


def downgrade() -> None:
    # Remove the Edit Script role
    op.execute("""
        DELETE FROM security_roles WHERE id = '10000000-0000-0000-0000-000000000037'::uuid
    """)
