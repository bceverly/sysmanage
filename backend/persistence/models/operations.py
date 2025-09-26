"""
Operations and management models for SysManage - user accounts, scripts, diagnostics, etc.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.persistence.db import Base
from backend.persistence.models.core import GUID


class UserAccount(Base):
    """
    This class holds the object mapping for the user_accounts table in the
    PostgreSQL database.
    """

    __tablename__ = "user_accounts"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(255), nullable=False)
    uid = Column(Integer, nullable=True)  # Linux/macOS user ID
    security_id = Column(String(255), nullable=True)  # Windows SID
    home_directory = Column(String(500), nullable=True)
    shell = Column(String(255), nullable=True)
    is_system_user = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="user_accounts")


class UserGroup(Base):
    """
    This class holds the object mapping for the user_groups table in the
    PostgreSQL database.
    """

    __tablename__ = "user_groups"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(255), nullable=False)
    gid = Column(Integer, nullable=True)  # Linux/macOS group ID
    security_id = Column(String(255), nullable=True)  # Windows SID
    is_system_group = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host", back_populates="user_groups")


class UserGroupMembership(Base):
    """
    This class holds the object mapping for the user_group_memberships table in the
    PostgreSQL database. This table stores many-to-many relationships between
    users and groups.
    """

    __tablename__ = "user_group_memberships"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    user_account_id = Column(
        GUID(), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    user_group_id = Column(
        GUID(), ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    host = relationship("Host")
    user_account = relationship("UserAccount")
    user_group = relationship("UserGroup")


class UpdateExecutionLog(Base):
    """
    This class holds the object mapping for the update_execution_log table in the
    PostgreSQL database. It tracks the execution of package updates.
    """

    __tablename__ = "update_execution_log"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String(255), nullable=False, index=True)
    from_version = Column(String(100), nullable=False)
    to_version = Column(String(100), nullable=False)
    package_manager = Column(String(50), nullable=False)
    execution_status = Column(
        String(20), nullable=False
    )  # pending, running, success, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    output_log = Column(Text, nullable=True)
    error_log = Column(Text, nullable=True)
    executed_by = Column(String(255), nullable=True)  # User who initiated the update
    execution_method = Column(String(50), nullable=True)  # manual, automatic, scheduled
    requires_reboot = Column(Boolean, nullable=False, default=False)
    reboot_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship back to Host
    host = relationship("Host")

    def __repr__(self):
        return f"<UpdateExecutionLog(id={self.id}, package_name='{self.package_name}', from='{self.from_version}', to='{self.to_version}', status='{self.execution_status}', host_id={self.host_id})>"


class MessageQueue(Base):
    """
    This class holds the object mapping for the message_queue table in the
    PostgreSQL database. This table is used for asynchronous message processing
    between the web server and agents.
    """

    __tablename__ = "message_queue"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), nullable=True)
    message_id = Column(String(36), nullable=False, index=True)  # UUID
    direction = Column(String(10), nullable=False, index=True)
    message_type = Column(String(50), nullable=False, index=True)
    message_data = Column(Text, nullable=False)  # JSON serialized message content
    status = Column(
        String(15), nullable=False, index=True
    )  # pending, processing, completed, failed, expired
    priority = Column(String(10), nullable=False, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_at = Column(
        DateTime(timezone=True), nullable=True, index=True
    )  # For delayed messages
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(
        String(36), nullable=True, index=True
    )  # For request-response correlation
    reply_to = Column(String(36), nullable=True)  # Response queue name
    expired_at = Column(
        DateTime(timezone=True), nullable=True, index=True
    )  # Message expiration

    def __repr__(self):
        return f"<MessageQueue(id={self.id}, message_id='{self.message_id}', direction='{self.direction}', type='{self.message_type}', status='{self.status}', host_id={self.host_id}, priority={self.priority})>"


# Create an index for efficient queue processing
Index(
    "idx_message_queue_processing",
    MessageQueue.direction,
    MessageQueue.status,
    MessageQueue.priority,
    MessageQueue.scheduled_at,
)


class QueueMetrics(Base):
    """
    This class holds the object mapping for the queue_metrics table in the
    PostgreSQL database. This table stores aggregated metrics about message
    queue performance and health.
    """

    __tablename__ = "queue_metrics"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    queue_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(
        String(50), nullable=False, index=True
    )  # throughput, latency, error_rate, queue_depth
    metric_value = Column(
        String(100), nullable=False
    )  # Flexible storage for different metric types
    aggregation_period = Column(String(20), nullable=False)  # minute, hour, day
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    sample_count = Column(
        Integer, nullable=True
    )  # Number of samples in this aggregation
    additional_data = Column(Text, nullable=True)  # JSON for additional metric metadata
    created_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<QueueMetrics(id={self.id}, queue='{self.queue_name}', type='{self.metric_type}', value='{self.metric_value}', period='{self.aggregation_period}')>"


class SavedScript(Base):
    """
    This class holds the object mapping for the saved_script table in the
    PostgreSQL database. It stores reusable scripts that can be executed on hosts.
    """

    __tablename__ = "saved_scripts"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    shell_type = Column(String(50), nullable=False)  # bash, sh, powershell, etc.
    platform = Column(String(50), nullable=True)  # linux, windows, macos, etc.
    run_as_user = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<SavedScript(id={self.id}, name='{self.name}', shell='{self.shell_type}', active={self.is_active})>"


class ScriptExecutionLog(Base):
    """
    This class holds the object mapping for the script_execution_log table in the
    PostgreSQL database. It tracks the execution of scripts on hosts.
    """

    __tablename__ = "script_execution_log"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    execution_id = Column(String(36), nullable=False, unique=True, index=True)  # UUID
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    saved_script_id = Column(
        GUID(), ForeignKey("saved_scripts.id", ondelete="SET NULL"), nullable=True
    )
    script_name = Column(
        String(255), nullable=True
    )  # Copy for when saved_script is deleted
    script_content = Column(Text, nullable=False)
    shell_type = Column(String(50), nullable=False)
    run_as_user = Column(String(100), nullable=True)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, running, completed, failed, timeout
    requested_by = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    exit_code = Column(Integer, nullable=True)
    stdout_output = Column(Text, nullable=True)
    stderr_output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    execution_uuid = Column(String(36), nullable=True, unique=True, index=True)

    # Relationships
    host = relationship("Host")
    saved_script = relationship("SavedScript")

    def __repr__(self):
        return f"<ScriptExecutionLog(id={self.id}, execution_id='{self.execution_id}', status='{self.status}', host_id={self.host_id})>"


class DiagnosticReport(Base):
    """
    This class holds the object mapping for the diagnostic_report table in the
    PostgreSQL database. It stores diagnostic data collected from hosts.
    """

    __tablename__ = "diagnostic_report"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    collection_id = Column(String(36), nullable=False, unique=True, index=True)  # UUID
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    requested_by = Column(String(255), nullable=False)
    collection_status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, collecting, completed, failed
    requested_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    collection_size_bytes = Column(BigInteger, nullable=True)
    files_collected = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # Diagnostic data - stored as JSON text
    system_logs = Column(Text, nullable=True)
    configuration_files = Column(Text, nullable=True)
    process_list = Column(Text, nullable=True)
    system_information = Column(Text, nullable=True)
    network_information = Column(Text, nullable=True)
    disk_usage = Column(Text, nullable=True)
    environment_variables = Column(Text, nullable=True)
    agent_logs = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    host = relationship("Host")

    def __repr__(self):
        return f"<DiagnosticReport(id={self.id}, collection_id='{self.collection_id}', status='{self.collection_status}', host_id={self.host_id})>"


class Tag(Base):
    """
    This class holds the object mapping for the tag table in the
    PostgreSQL database.
    """

    __tablename__ = "tags"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    hosts = relationship(
        "Host", secondary="host_tags", back_populates="tags", lazy="dynamic"
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"


class HostTag(Base):
    """
    This class holds the object mapping for the host_tags table in the
    PostgreSQL database. This is a many-to-many relationship table between
    hosts and tags.
    """

    __tablename__ = "host_tags"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(GUID(), ForeignKey("host.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(GUID(), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<HostTag(id={self.id}, host_id={self.host_id}, tag_id={self.tag_id})>"


class PasswordResetToken(Base):
    """
    This class holds the object mapping for the password_reset_token table in the
    PostgreSQL database.
    """

    __tablename__ = "password_reset_token"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    user = relationship("User")

    def __repr__(self):
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, expires_at='{self.expires_at}')>"


class UbuntuProInfo(Base):
    """
    This class holds the object mapping for the ubuntu_pro_info table in the
    PostgreSQL database. It stores Ubuntu Pro subscription information for hosts.
    """

    __tablename__ = "ubuntu_pro_info"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(
        GUID(),
        ForeignKey("host.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    attached = Column(Boolean, nullable=False, default=False)
    subscription_name = Column(String(255), nullable=True)
    account_name = Column(String(255), nullable=True)
    contract_name = Column(String(255), nullable=True)
    tech_support_level = Column(String(100), nullable=True)
    expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    host = relationship("Host")
    services = relationship(
        "UbuntuProService",
        back_populates="ubuntu_pro_info",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<UbuntuProInfo(id={self.id}, host_id={self.host_id}, attached={self.attached})>"


class UbuntuProService(Base):
    """
    This class holds the object mapping for the ubuntu_pro_service table in the
    PostgreSQL database. It stores individual Ubuntu Pro services for each host.
    """

    __tablename__ = "ubuntu_pro_service"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    ubuntu_pro_info_id = Column(
        GUID(), ForeignKey("ubuntu_pro_info.id", ondelete="CASCADE"), nullable=False
    )
    service_name = Column(String(100), nullable=False)
    entitled = Column(String(20), nullable=True)  # "yes", "no", etc.
    status = Column(String(20), nullable=True)  # "enabled", "disabled", etc.
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship
    ubuntu_pro_info = relationship("UbuntuProInfo", back_populates="services")

    def __repr__(self):
        return f"<UbuntuProService(id={self.id}, service_name='{self.service_name}', entitled='{self.entitled}', status='{self.status}')>"


class UbuntuProSettings(Base):
    """
    This class holds the object mapping for the ubuntu_pro_settings table in the
    PostgreSQL database. It stores global Ubuntu Pro configuration.
    """

    __tablename__ = "ubuntu_pro_settings"
    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    organization_name = Column(String(255), nullable=True)
    master_key = Column(String(255), nullable=True)  # Encrypted Ubuntu Pro key
    auto_attach_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    def __repr__(self):
        return f"<UbuntuProSettings(id={self.id}, organization='{self.organization_name}', auto_attach={self.auto_attach_enabled})>"
