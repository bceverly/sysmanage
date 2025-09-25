"""create_complete_schema_from_scratch

Revision ID: 6dd4ca89b6b8
Revises:
Create Date: 2025-09-25 16:44:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '6dd4ca89b6b8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create all tables for the complete SysManage schema matching current models exactly

    # User table - matches User model in core.py
    op.create_table('user',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('userid', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('last_access', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('profile_image', sa.LargeBinary(), nullable=True),
        sa.Column('profile_image_type', sa.String(length=10), nullable=True),
        sa.Column('profile_image_uploaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('userid')
    )
    op.create_index('ix_user_id', 'user', ['id'])
    op.create_index('ix_user_userid', 'user', ['userid'])

    # BearerToken table - matches BearerToken model in core.py
    op.create_table('bearer_token',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )

    # Host table - matches Host model in core.py with ALL fields
    op.create_table('host',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('fqdn', sa.String(), nullable=True),
        sa.Column('ipv4', sa.String(), nullable=True),
        sa.Column('ipv6', sa.String(), nullable=True),
        sa.Column('host_token', sa.String(length=256), nullable=True),
        sa.Column('last_access', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='up'),
        sa.Column('approval_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('client_certificate', sa.Text(), nullable=True),
        sa.Column('certificate_serial', sa.String(length=64), nullable=True),
        sa.Column('certificate_issued_at', sa.DateTime(timezone=True), nullable=True),
        # OS Version fields
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('platform_release', sa.String(length=100), nullable=True),
        sa.Column('platform_version', sa.Text(), nullable=True),
        sa.Column('machine_architecture', sa.String(length=50), nullable=True),
        sa.Column('processor', sa.String(length=100), nullable=True),
        sa.Column('os_details', sa.Text(), nullable=True),
        sa.Column('os_version_updated_at', sa.DateTime(timezone=True), nullable=True),
        # Hardware inventory fields
        sa.Column('cpu_vendor', sa.String(length=100), nullable=True),
        sa.Column('cpu_model', sa.String(length=200), nullable=True),
        sa.Column('cpu_cores', sa.Integer(), nullable=True),
        sa.Column('cpu_threads', sa.Integer(), nullable=True),
        sa.Column('cpu_frequency_mhz', sa.Integer(), nullable=True),
        sa.Column('memory_total_mb', sa.BigInteger(), nullable=True),
        sa.Column('storage_details', sa.Text(), nullable=True),
        sa.Column('network_details', sa.Text(), nullable=True),
        sa.Column('hardware_details', sa.Text(), nullable=True),
        sa.Column('hardware_updated_at', sa.DateTime(timezone=True), nullable=True),
        # Software inventory fields
        sa.Column('software_updated_at', sa.DateTime(timezone=True), nullable=True),
        # User access data timestamp
        sa.Column('user_access_updated_at', sa.DateTime(timezone=True), nullable=True),
        # Diagnostics request tracking
        sa.Column('diagnostics_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('diagnostics_request_status', sa.String(length=50), nullable=True),
        # Update management fields
        sa.Column('reboot_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reboot_required_updated_at', sa.DateTime(timezone=True), nullable=True),
        # Agent privilege status
        sa.Column('is_agent_privileged', sa.Boolean(), nullable=True, server_default='false'),
        # Script execution permission
        sa.Column('script_execution_enabled', sa.Boolean(), nullable=False, server_default='false'),
        # Available shells on the host
        sa.Column('enabled_shells', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('host_token')
    )
    op.create_index('ix_host_id', 'host', ['id'])
    op.create_index('ix_host_fqdn', 'host', ['fqdn'])

    # HostCertificate table - matches HostCertificate model in host_certificate.py
    op.create_table('host_certificates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('certificate_name', sa.String(length=500), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('issuer', sa.Text(), nullable=True),
        sa.Column('not_before', sa.DateTime(timezone=True), nullable=True),
        sa.Column('not_after', sa.DateTime(timezone=True), nullable=True),
        sa.Column('serial_number', sa.String(length=100), nullable=True),
        sa.Column('fingerprint_sha256', sa.String(length=64), nullable=True),
        sa.Column('is_ca', sa.Boolean(), nullable=True),
        sa.Column('key_usage', sa.String(length=500), nullable=True),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_host_certificates_file_path', 'host_certificates', ['file_path'])
    op.create_index('ix_host_certificates_not_after', 'host_certificates', ['not_after'])
    op.create_index('ix_host_certificates_fingerprint_sha256', 'host_certificates', ['fingerprint_sha256'])
    op.create_index('ix_host_certificates_collected_at', 'host_certificates', ['collected_at'])

    # StorageDevice table - matches StorageDevice model in hardware.py
    op.create_table('storage_device',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_name', sa.String(length=255), nullable=False),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('mount_point', sa.String(length=255), nullable=True),
        sa.Column('filesystem', sa.String(length=100), nullable=True),
        sa.Column('total_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('used_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('available_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('device_details', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # NetworkInterface table - matches NetworkInterface model in hardware.py
    op.create_table('network_interface',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('interface_name', sa.String(length=255), nullable=False),
        sa.Column('interface_type', sa.String(length=50), nullable=True),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('ipv4_address', sa.String(length=15), nullable=True),
        sa.Column('ipv6_address', sa.String(length=39), nullable=True),
        sa.Column('netmask', sa.String(length=15), nullable=True),
        sa.Column('broadcast', sa.String(length=15), nullable=True),
        sa.Column('mtu', sa.Integer(), nullable=True),
        sa.Column('speed_mbps', sa.Integer(), nullable=True),
        sa.Column('is_up', sa.Boolean(), nullable=True),
        sa.Column('interface_details', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # SoftwarePackage table - matches SoftwarePackage model in software.py
    op.create_table('software_package',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_version', sa.String(length=100), nullable=False),
        sa.Column('package_description', sa.Text(), nullable=True),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('architecture', sa.String(length=50), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('vendor', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('license', sa.String(length=255), nullable=True),
        sa.Column('install_path', sa.String(length=500), nullable=True),
        sa.Column('install_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_system_package', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_software_package_package_name', 'software_package', ['package_name'])

    # PackageUpdate table - matches PackageUpdate model in software.py
    op.create_table('package_update',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('current_version', sa.String(length=100), nullable=False),
        sa.Column('available_version', sa.String(length=100), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('update_type', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('requires_reboot', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_package_update_package_name', 'package_update', ['package_name'])

    # AvailablePackage table - matches AvailablePackage model in software.py
    op.create_table('available_packages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_version', sa.String(length=100), nullable=False),
        sa.Column('package_description', sa.Text(), nullable=True),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('os_name', sa.String(length=100), nullable=False),
        sa.Column('os_version', sa.String(length=100), nullable=False),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_available_packages_package_name', 'available_packages', ['package_name'])
    op.create_index('ix_available_packages_package_manager', 'available_packages', ['package_manager'])
    op.create_index('ix_available_packages_os_name', 'available_packages', ['os_name'])
    op.create_index('ix_available_packages_os_version', 'available_packages', ['os_version'])

    # SoftwareInstallationLog table - matches SoftwareInstallationLog model in software.py
    op.create_table('software_installation_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('requested_version', sa.String(length=100), nullable=True),
        sa.Column('requested_by', sa.String(length=100), nullable=False),
        sa.Column('installation_id', sa.String(length=36), nullable=False, unique=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('installed_version', sa.String(length=100), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('installation_log', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_software_installation_log_installation_id', 'software_installation_log', ['installation_id'])
    op.create_index('ix_software_installation_log_status', 'software_installation_log', ['status'])
    op.create_index('ix_software_installation_log_requested_at', 'software_installation_log', ['requested_at'])

    # InstallationRequest table - matches InstallationRequest model in software.py
    op.create_table('installation_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_by', sa.String(length=100), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('operation_type', sa.String(length=20), nullable=False, server_default='install'),
        sa.Column('result_log', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_installation_requests_requested_at', 'installation_requests', ['requested_at'])
    op.create_index('ix_installation_requests_status', 'installation_requests', ['status'])
    op.create_index('ix_installation_requests_operation_type', 'installation_requests', ['operation_type'])

    # InstallationPackage table - matches InstallationPackage model in software.py
    op.create_table('installation_packages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('installation_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['installation_request_id'], ['installation_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_installation_packages_installation_request_id', 'installation_packages', ['installation_request_id'])

    # UserAccount table - matches UserAccount model in operations.py
    op.create_table('user_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('uid', sa.Integer(), nullable=True),
        sa.Column('home_directory', sa.String(length=500), nullable=True),
        sa.Column('shell', sa.String(length=255), nullable=True),
        sa.Column('is_system_user', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # UserGroup table - matches UserGroup model in operations.py
    op.create_table('user_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_name', sa.String(length=255), nullable=False),
        sa.Column('gid', sa.Integer(), nullable=True),
        sa.Column('is_system_group', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # UserGroupMembership table - matches UserGroupMembership model in operations.py
    op.create_table('user_group_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_account_id'], ['user_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_group_id'], ['user_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # UpdateExecutionLog table - matches UpdateExecutionLog model in operations.py
    op.create_table('update_execution_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('from_version', sa.String(length=100), nullable=False),
        sa.Column('to_version', sa.String(length=100), nullable=False),
        sa.Column('package_manager', sa.String(length=50), nullable=False),
        sa.Column('execution_status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('output_log', sa.Text(), nullable=True),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('executed_by', sa.String(length=255), nullable=True),
        sa.Column('execution_method', sa.String(length=50), nullable=True),
        sa.Column('requires_reboot', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reboot_requested', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_update_execution_log_package_name', 'update_execution_log', ['package_name'])

    # MessageQueue table - matches MessageQueue model in operations.py
    op.create_table('message_queue',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('message_id', sa.String(length=36), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('message_type', sa.String(length=50), nullable=False),
        sa.Column('message_data', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=15), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('correlation_id', sa.String(length=36), nullable=True),
        sa.Column('reply_to', sa.String(length=36), nullable=True),
        sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_message_queue_message_id', 'message_queue', ['message_id'])
    op.create_index('ix_message_queue_direction', 'message_queue', ['direction'])
    op.create_index('ix_message_queue_message_type', 'message_queue', ['message_type'])
    op.create_index('ix_message_queue_status', 'message_queue', ['status'])
    op.create_index('ix_message_queue_priority', 'message_queue', ['priority'])
    op.create_index('ix_message_queue_created_at', 'message_queue', ['created_at'])
    op.create_index('ix_message_queue_scheduled_at', 'message_queue', ['scheduled_at'])
    op.create_index('ix_message_queue_correlation_id', 'message_queue', ['correlation_id'])
    op.create_index('ix_message_queue_expired_at', 'message_queue', ['expired_at'])

    # Create composite index for efficient queue processing
    op.create_index('idx_message_queue_processing', 'message_queue', ['direction', 'status', 'priority', 'scheduled_at'])

    # QueueMetrics table - matches QueueMetrics model in operations.py
    op.create_table('queue_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('queue_name', sa.String(length=100), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('metric_value', sa.String(length=100), nullable=False),
        sa.Column('aggregation_period', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=True),
        sa.Column('additional_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_queue_metrics_queue_name', 'queue_metrics', ['queue_name'])
    op.create_index('ix_queue_metrics_metric_type', 'queue_metrics', ['metric_type'])
    op.create_index('ix_queue_metrics_period_start', 'queue_metrics', ['period_start'])

    # SavedScript table - matches SavedScript model in operations.py
    op.create_table('saved_scripts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('shell_type', sa.String(length=50), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=True),
        sa.Column('run_as_user', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_saved_scripts_name', 'saved_scripts', ['name'])
    op.create_index('ix_saved_scripts_is_active', 'saved_scripts', ['is_active'])

    # ScriptExecutionLog table - matches ScriptExecutionLog model in operations.py
    op.create_table('script_execution_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False, unique=True),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('saved_script_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('script_name', sa.String(length=255), nullable=True),
        sa.Column('script_content', sa.Text(), nullable=False),
        sa.Column('shell_type', sa.String(length=50), nullable=False),
        sa.Column('run_as_user', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('requested_by', sa.String(length=255), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('stdout_output', sa.Text(), nullable=True),
        sa.Column('stderr_output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('execution_uuid', sa.String(length=36), nullable=True, unique=True),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['saved_script_id'], ['saved_scripts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_script_execution_log_execution_id', 'script_execution_log', ['execution_id'])
    op.create_index('ix_script_execution_log_execution_uuid', 'script_execution_log', ['execution_uuid'])

    # DiagnosticReport table - matches DiagnosticReport model in operations.py
    op.create_table('diagnostic_report',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('collection_id', sa.String(length=36), nullable=False, unique=True),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_by', sa.String(length=255), nullable=False),
        sa.Column('collection_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('collection_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('files_collected', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('system_logs', sa.Text(), nullable=True),
        sa.Column('configuration_files', sa.Text(), nullable=True),
        sa.Column('process_list', sa.Text(), nullable=True),
        sa.Column('system_information', sa.Text(), nullable=True),
        sa.Column('network_information', sa.Text(), nullable=True),
        sa.Column('disk_usage', sa.Text(), nullable=True),
        sa.Column('environment_variables', sa.Text(), nullable=True),
        sa.Column('agent_logs', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_diagnostic_report_collection_id', 'diagnostic_report', ['collection_id'])

    # Tag table - matches Tag model in operations.py
    op.create_table('tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tags_name', 'tags', ['name'])

    # HostTag table - matches HostTag model in operations.py
    op.create_table('host_tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # PasswordResetToken table - matches PasswordResetToken model in operations.py
    op.create_table('password_reset_token',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_password_reset_token_token', 'password_reset_token', ['token'])

    # UbuntuProInfo table - matches UbuntuProInfo model in operations.py
    op.create_table('ubuntu_pro_info',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('host_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('attached', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('subscription_name', sa.String(length=255), nullable=True),
        sa.Column('account_name', sa.String(length=255), nullable=True),
        sa.Column('contract_name', sa.String(length=255), nullable=True),
        sa.Column('tech_support_level', sa.String(length=100), nullable=True),
        sa.Column('expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # UbuntuProService table - matches UbuntuProService model in operations.py
    op.create_table('ubuntu_pro_service',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ubuntu_pro_info_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_name', sa.String(length=100), nullable=False),
        sa.Column('entitled', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['ubuntu_pro_info_id'], ['ubuntu_pro_info.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # UbuntuProSettings table - matches UbuntuProSettings model in operations.py
    op.create_table('ubuntu_pro_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_name', sa.String(length=255), nullable=True),
        sa.Column('master_key', sa.String(length=255), nullable=True),
        sa.Column('auto_attach_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Secret table - matches Secret model in secret.py
    op.create_table('secrets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('secret_type', sa.String(length=50), nullable=False),
        sa.Column('secret_subtype', sa.String(length=30), nullable=True),
        sa.Column('vault_token', sa.Text(), nullable=False),
        sa.Column('vault_path', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column('updated_by', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_secrets_name', 'secrets', ['name'])
    op.create_index('ix_secrets_secret_type', 'secrets', ['secret_type'])
    op.create_index('ix_secrets_created_at', 'secrets', ['created_at'])


def downgrade() -> None:
    # Drop all tables in reverse order of creation
    op.drop_table('secrets')
    op.drop_table('ubuntu_pro_settings')
    op.drop_table('ubuntu_pro_service')
    op.drop_table('ubuntu_pro_info')
    op.drop_table('password_reset_token')
    op.drop_table('host_tags')
    op.drop_table('tags')
    op.drop_table('diagnostic_report')
    op.drop_table('script_execution_log')
    op.drop_table('saved_scripts')
    op.drop_table('queue_metrics')
    op.drop_table('message_queue')
    op.drop_table('update_execution_log')
    op.drop_table('user_group_memberships')
    op.drop_table('user_groups')
    op.drop_table('user_accounts')
    op.drop_table('installation_packages')
    op.drop_table('installation_requests')
    op.drop_table('software_installation_log')
    op.drop_table('available_packages')
    op.drop_table('package_update')
    op.drop_table('software_package')
    op.drop_table('network_interface')
    op.drop_table('storage_device')
    op.drop_table('host_certificates')
    op.drop_table('host')
    op.drop_table('bearer_token')
    op.drop_table('user')