"""add_security_roles_and_permissions

Revision ID: 54fcacb0e742
Revises: e8ed9f2e620f
Create Date: 2025-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '54fcacb0e742'
down_revision: Union[str, None] = 'e8ed9f2e620f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create security_role_groups table
    op.create_table(
        'security_role_groups',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create security_roles table
    op.create_table(
        'security_roles',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('group_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['security_role_groups.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('name')
    )

    # Create user_security_roles mapping table
    op.create_table(
        'user_security_roles',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', UUID(as_uuid=True), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('granted_by', UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['security_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['user.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('user_id', 'role_id', name='unique_user_role')
    )

    # Insert security role groups using raw SQL to work with UUIDs
    op.execute("""
        INSERT INTO security_role_groups (id, name, description) VALUES
        ('00000000-0000-0000-0000-000000000001'::uuid, 'Host', 'Permissions related to host management'),
        ('00000000-0000-0000-0000-000000000002'::uuid, 'Package', 'Permissions related to package management'),
        ('00000000-0000-0000-0000-000000000003'::uuid, 'Secrets', 'Permissions related to secret management'),
        ('00000000-0000-0000-0000-000000000004'::uuid, 'User', 'Permissions related to user management'),
        ('00000000-0000-0000-0000-000000000005'::uuid, 'Scripts', 'Permissions related to script management'),
        ('00000000-0000-0000-0000-000000000006'::uuid, 'Reports', 'Permissions related to report generation'),
        ('00000000-0000-0000-0000-000000000007'::uuid, 'Integrations', 'Permissions related to system integrations'),
        ('00000000-0000-0000-0000-000000000008'::uuid, 'Ubuntu Pro', 'Permissions related to Ubuntu Pro management')
    """)

    # Insert security roles using raw SQL to work with UUIDs
    op.execute("""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        -- Host group
        ('10000000-0000-0000-0000-000000000001'::uuid, 'Approve Host Registration', 'Approve new host registrations', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000002'::uuid, 'Delete Host', 'Delete hosts from the system', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000003'::uuid, 'View Host Details', 'View detailed host information', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000004'::uuid, 'Reboot Host', 'Reboot hosts', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000005'::uuid, 'Shutdown Host', 'Shutdown hosts', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000006'::uuid, 'Edit Tags', 'Edit host tags', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000010'::uuid, 'Stop Host Service', 'Stop services on hosts', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000011'::uuid, 'Start Host Service', 'Start services on hosts', '00000000-0000-0000-0000-000000000001'::uuid),
        ('10000000-0000-0000-0000-000000000012'::uuid, 'Restart Host Service', 'Restart services on hosts', '00000000-0000-0000-0000-000000000001'::uuid),

        -- Package group
        ('10000000-0000-0000-0000-000000000007'::uuid, 'Add Package', 'Add packages to hosts', '00000000-0000-0000-0000-000000000002'::uuid),
        ('10000000-0000-0000-0000-000000000020'::uuid, 'Apply Software Update', 'Apply software updates to hosts', '00000000-0000-0000-0000-000000000002'::uuid),
        ('10000000-0000-0000-0000-000000000021'::uuid, 'Apply Host OS Upgrade', 'Apply OS upgrades to hosts', '00000000-0000-0000-0000-000000000002'::uuid),

        -- Secrets group
        ('10000000-0000-0000-0000-000000000008'::uuid, 'Deploy SSH Key', 'Deploy SSH keys to hosts', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000009'::uuid, 'Deploy Certificate', 'Deploy certificates to hosts', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000022'::uuid, 'Add Secret', 'Add secrets to the vault', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000023'::uuid, 'Delete Secret', 'Delete secrets from the vault', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000024'::uuid, 'Edit Secret', 'Edit existing secrets', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000032'::uuid, 'Stop Vault', 'Stop the vault service', '00000000-0000-0000-0000-000000000003'::uuid),
        ('10000000-0000-0000-0000-000000000033'::uuid, 'Start Vault', 'Start the vault service', '00000000-0000-0000-0000-000000000003'::uuid),

        -- User group
        ('10000000-0000-0000-0000-000000000015'::uuid, 'Add User', 'Add new users to the system', '00000000-0000-0000-0000-000000000004'::uuid),
        ('10000000-0000-0000-0000-000000000016'::uuid, 'Edit User', 'Edit existing users', '00000000-0000-0000-0000-000000000004'::uuid),
        ('10000000-0000-0000-0000-000000000017'::uuid, 'Lock User', 'Lock user accounts', '00000000-0000-0000-0000-000000000004'::uuid),
        ('10000000-0000-0000-0000-000000000018'::uuid, 'Unlock User', 'Unlock user accounts', '00000000-0000-0000-0000-000000000004'::uuid),
        ('10000000-0000-0000-0000-000000000019'::uuid, 'Delete User', 'Delete users from the system', '00000000-0000-0000-0000-000000000004'::uuid),

        -- Scripts group
        ('10000000-0000-0000-0000-000000000025'::uuid, 'Add Script', 'Add new scripts', '00000000-0000-0000-0000-000000000005'::uuid),
        ('10000000-0000-0000-0000-000000000026'::uuid, 'Delete Script', 'Delete scripts', '00000000-0000-0000-0000-000000000005'::uuid),
        ('10000000-0000-0000-0000-000000000027'::uuid, 'Run Script', 'Execute scripts on hosts', '00000000-0000-0000-0000-000000000005'::uuid),
        ('10000000-0000-0000-0000-000000000028'::uuid, 'Delete Script Execution', 'Delete script execution history', '00000000-0000-0000-0000-000000000005'::uuid),

        -- Reports group
        ('10000000-0000-0000-0000-000000000029'::uuid, 'View Report', 'View system reports', '00000000-0000-0000-0000-000000000006'::uuid),
        ('10000000-0000-0000-0000-000000000030'::uuid, 'Generate PDF Report', 'Generate PDF reports', '00000000-0000-0000-0000-000000000006'::uuid),

        -- Integrations group
        ('10000000-0000-0000-0000-000000000031'::uuid, 'Delete Queue Message', 'Delete messages from the queue', '00000000-0000-0000-0000-000000000007'::uuid),
        ('10000000-0000-0000-0000-000000000034'::uuid, 'Enable Grafana Integration', 'Enable and configure Grafana integration', '00000000-0000-0000-0000-000000000007'::uuid),

        -- Ubuntu Pro group
        ('10000000-0000-0000-0000-000000000013'::uuid, 'Attach Ubuntu Pro', 'Attach Ubuntu Pro to hosts', '00000000-0000-0000-0000-000000000008'::uuid),
        ('10000000-0000-0000-0000-000000000014'::uuid, 'Detach Ubuntu Pro', 'Detach Ubuntu Pro from hosts', '00000000-0000-0000-0000-000000000008'::uuid),
        ('10000000-0000-0000-0000-000000000035'::uuid, 'Change Ubuntu Pro Master Key', 'Change the Ubuntu Pro master key', '00000000-0000-0000-0000-000000000008'::uuid)
    """)

    # Create indexes for better performance
    op.create_index('idx_security_roles_group_id', 'security_roles', ['group_id'])
    op.create_index('idx_user_security_roles_user_id', 'user_security_roles', ['user_id'])
    op.create_index('idx_user_security_roles_role_id', 'user_security_roles', ['role_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_user_security_roles_role_id', table_name='user_security_roles')
    op.drop_index('idx_user_security_roles_user_id', table_name='user_security_roles')
    op.drop_index('idx_security_roles_group_id', table_name='security_roles')

    # Drop tables in reverse order
    op.drop_table('user_security_roles')
    op.drop_table('security_roles')
    op.drop_table('security_role_groups')
