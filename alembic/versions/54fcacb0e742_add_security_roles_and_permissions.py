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
    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

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
    # SQLite doesn't support ::uuid type casting, PostgreSQL requires it
    uuid_cast = '' if is_sqlite else '::uuid'
    op.execute(f"""
        INSERT INTO security_role_groups (id, name, description) VALUES
        ('00000000-0000-0000-0000-000000000001'{uuid_cast}, 'Host', 'Permissions related to host management'),
        ('00000000-0000-0000-0000-000000000002'{uuid_cast}, 'Package', 'Permissions related to package management'),
        ('00000000-0000-0000-0000-000000000003'{uuid_cast}, 'Secrets', 'Permissions related to secret management'),
        ('00000000-0000-0000-0000-000000000004'{uuid_cast}, 'User', 'Permissions related to user management'),
        ('00000000-0000-0000-0000-000000000005'{uuid_cast}, 'Scripts', 'Permissions related to script management'),
        ('00000000-0000-0000-0000-000000000006'{uuid_cast}, 'Reports', 'Permissions related to report generation'),
        ('00000000-0000-0000-0000-000000000007'{uuid_cast}, 'Integrations', 'Permissions related to system integrations'),
        ('00000000-0000-0000-0000-000000000008'{uuid_cast}, 'Ubuntu Pro', 'Permissions related to Ubuntu Pro management')
    """)

    # Insert security roles using raw SQL to work with UUIDs
    op.execute(f"""
        INSERT INTO security_roles (id, name, description, group_id) VALUES
        -- Host group
        ('10000000-0000-0000-0000-000000000001'{uuid_cast}, 'Approve Host Registration', 'Approve new host registrations', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000002'{uuid_cast}, 'Delete Host', 'Delete hosts from the system', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000003'{uuid_cast}, 'View Host Details', 'View detailed host information', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000004'{uuid_cast}, 'Reboot Host', 'Reboot hosts', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000005'{uuid_cast}, 'Shutdown Host', 'Shutdown hosts', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000006'{uuid_cast}, 'Edit Tags', 'Edit host tags', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000010'{uuid_cast}, 'Stop Host Service', 'Stop services on hosts', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000011'{uuid_cast}, 'Start Host Service', 'Start services on hosts', '00000000-0000-0000-0000-000000000001'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000012'{uuid_cast}, 'Restart Host Service', 'Restart services on hosts', '00000000-0000-0000-0000-000000000001'{uuid_cast}),

        -- Package group
        ('10000000-0000-0000-0000-000000000007'{uuid_cast}, 'Add Package', 'Add packages to hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000020'{uuid_cast}, 'Apply Software Update', 'Apply software updates to hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000021'{uuid_cast}, 'Apply Host OS Upgrade', 'Apply OS upgrades to hosts', '00000000-0000-0000-0000-000000000002'{uuid_cast}),

        -- Secrets group
        ('10000000-0000-0000-0000-000000000008'{uuid_cast}, 'Deploy SSH Key', 'Deploy SSH keys to hosts', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000009'{uuid_cast}, 'Deploy Certificate', 'Deploy certificates to hosts', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000022'{uuid_cast}, 'Add Secret', 'Add secrets to the vault', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000023'{uuid_cast}, 'Delete Secret', 'Delete secrets from the vault', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000024'{uuid_cast}, 'Edit Secret', 'Edit existing secrets', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000032'{uuid_cast}, 'Stop Vault', 'Stop the vault service', '00000000-0000-0000-0000-000000000003'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000033'{uuid_cast}, 'Start Vault', 'Start the vault service', '00000000-0000-0000-0000-000000000003'{uuid_cast}),

        -- User group
        ('10000000-0000-0000-0000-000000000015'{uuid_cast}, 'Add User', 'Add new users to the system', '00000000-0000-0000-0000-000000000004'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000016'{uuid_cast}, 'Edit User', 'Edit existing users', '00000000-0000-0000-0000-000000000004'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000017'{uuid_cast}, 'Lock User', 'Lock user accounts', '00000000-0000-0000-0000-000000000004'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000018'{uuid_cast}, 'Unlock User', 'Unlock user accounts', '00000000-0000-0000-0000-000000000004'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000019'{uuid_cast}, 'Delete User', 'Delete users from the system', '00000000-0000-0000-0000-000000000004'{uuid_cast}),

        -- Scripts group
        ('10000000-0000-0000-0000-000000000025'{uuid_cast}, 'Add Script', 'Add new scripts', '00000000-0000-0000-0000-000000000005'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000026'{uuid_cast}, 'Delete Script', 'Delete scripts', '00000000-0000-0000-0000-000000000005'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000027'{uuid_cast}, 'Run Script', 'Execute scripts on hosts', '00000000-0000-0000-0000-000000000005'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000028'{uuid_cast}, 'Delete Script Execution', 'Delete script execution history', '00000000-0000-0000-0000-000000000005'{uuid_cast}),

        -- Reports group
        ('10000000-0000-0000-0000-000000000029'{uuid_cast}, 'View Report', 'View system reports', '00000000-0000-0000-0000-000000000006'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000030'{uuid_cast}, 'Generate PDF Report', 'Generate PDF reports', '00000000-0000-0000-0000-000000000006'{uuid_cast}),

        -- Integrations group
        ('10000000-0000-0000-0000-000000000031'{uuid_cast}, 'Delete Queue Message', 'Delete messages from the queue', '00000000-0000-0000-0000-000000000007'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000034'{uuid_cast}, 'Enable Grafana Integration', 'Enable and configure Grafana integration', '00000000-0000-0000-0000-000000000007'{uuid_cast}),

        -- Ubuntu Pro group
        ('10000000-0000-0000-0000-000000000013'{uuid_cast}, 'Attach Ubuntu Pro', 'Attach Ubuntu Pro to hosts', '00000000-0000-0000-0000-000000000008'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000014'{uuid_cast}, 'Detach Ubuntu Pro', 'Detach Ubuntu Pro from hosts', '00000000-0000-0000-0000-000000000008'{uuid_cast}),
        ('10000000-0000-0000-0000-000000000035'{uuid_cast}, 'Change Ubuntu Pro Master Key', 'Change the Ubuntu Pro master key', '00000000-0000-0000-0000-000000000008'{uuid_cast})
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
