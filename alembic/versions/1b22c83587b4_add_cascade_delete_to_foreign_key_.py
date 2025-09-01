"""Add CASCADE delete to foreign key constraints

Revision ID: 1b22c83587b4
Revises: b8fdbd25e034
Create Date: 2025-09-01 15:03:16.949761

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b22c83587b4'
down_revision: Union[str, None] = 'b8fdbd25e034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add CASCADE delete to all foreign key constraints that reference host(id)

    # Drop existing foreign key constraints
    op.drop_constraint('storage_devices_host_id_fkey', 'storage_devices', type_='foreignkey')
    op.drop_constraint('network_interfaces_host_id_fkey', 'network_interfaces', type_='foreignkey')
    op.drop_constraint('user_accounts_host_id_fkey', 'user_accounts', type_='foreignkey')
    op.drop_constraint('user_groups_host_id_fkey', 'user_groups', type_='foreignkey')
    op.drop_constraint('software_packages_host_id_fkey', 'software_packages', type_='foreignkey')

    # Recreate foreign key constraints with CASCADE delete
    op.create_foreign_key('storage_devices_host_id_fkey', 'storage_devices', 'host', ['host_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('network_interfaces_host_id_fkey', 'network_interfaces', 'host', ['host_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('user_accounts_host_id_fkey', 'user_accounts', 'host', ['host_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('user_groups_host_id_fkey', 'user_groups', 'host', ['host_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('software_packages_host_id_fkey', 'software_packages', 'host', ['host_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Revert CASCADE delete from foreign key constraints

    # Drop CASCADE foreign key constraints
    op.drop_constraint('storage_devices_host_id_fkey', 'storage_devices', type_='foreignkey')
    op.drop_constraint('network_interfaces_host_id_fkey', 'network_interfaces', type_='foreignkey')
    op.drop_constraint('user_accounts_host_id_fkey', 'user_accounts', type_='foreignkey')
    op.drop_constraint('user_groups_host_id_fkey', 'user_groups', type_='foreignkey')
    op.drop_constraint('software_packages_host_id_fkey', 'software_packages', type_='foreignkey')

    # Recreate foreign key constraints without CASCADE delete
    op.create_foreign_key('storage_devices_host_id_fkey', 'storage_devices', 'host', ['host_id'], ['id'])
    op.create_foreign_key('network_interfaces_host_id_fkey', 'network_interfaces', 'host', ['host_id'], ['id'])
    op.create_foreign_key('user_accounts_host_id_fkey', 'user_accounts', 'host', ['host_id'], ['id'])
    op.create_foreign_key('user_groups_host_id_fkey', 'user_groups', 'host', ['host_id'], ['id'])
    op.create_foreign_key('software_packages_host_id_fkey', 'software_packages', 'host', ['host_id'], ['id'])
