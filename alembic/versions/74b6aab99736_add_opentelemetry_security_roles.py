"""add_opentelemetry_security_roles

Revision ID: 74b6aab99736
Revises: d035c364de42
Create Date: 2025-10-05 07:10:13.223082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74b6aab99736'
down_revision: Union[str, None] = 'd035c364de42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Add OpenTelemetry roles to the Integrations group
    # Using role IDs 38-41 to continue the sequence
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        ('10000000-0000-0000-0000-000000000038'{uuid_cast}, 'Deploy OpenTelemetry', 'Deploy OpenTelemetry to hosts', '00000000-0000-0000-0000-000000000007'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000039'{uuid_cast}, 'Start OpenTelemetry Service', 'Start OpenTelemetry service on hosts', '00000000-0000-0000-0000-000000000007'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000040'{uuid_cast}, 'Stop OpenTelemetry Service', 'Stop OpenTelemetry service on hosts', '00000000-0000-0000-0000-000000000007'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000041'{uuid_cast}, 'Restart OpenTelemetry Service', 'Restart OpenTelemetry service on hosts', '00000000-0000-0000-0000-000000000007'{uuid_cast})
    """)


def downgrade() -> None:
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    uuid_cast = '' if is_sqlite else '::uuid'

    # Remove the OpenTelemetry roles
    op.execute(f"""
        DELETE FROM security_roles WHERE id IN (
            '10000000-0000-0000-0000-000000000038'{uuid_cast},
            '10000000-0000-0000-0000-000000000039'{uuid_cast},
            '10000000-0000-0000-0000-000000000040'{uuid_cast},
            '10000000-0000-0000-0000-000000000041'{uuid_cast}
        )
    """)
