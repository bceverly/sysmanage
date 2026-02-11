"""
Tests for backend/persistence/models/operations.py module.
Tests all operations and management models.
"""

import uuid
from datetime import datetime, timezone

import pytest


class TestUserAccountModel:
    """Tests for UserAccount model."""

    def test_table_name(self):
        """Test UserAccount table name."""
        from backend.persistence.models.operations import UserAccount

        assert UserAccount.__tablename__ == "user_accounts"

    def test_columns_exist(self):
        """Test UserAccount has expected columns."""
        from backend.persistence.models.operations import UserAccount

        assert hasattr(UserAccount, "id")
        assert hasattr(UserAccount, "host_id")
        assert hasattr(UserAccount, "username")
        assert hasattr(UserAccount, "uid")
        assert hasattr(UserAccount, "security_id")
        assert hasattr(UserAccount, "home_directory")
        assert hasattr(UserAccount, "shell")
        assert hasattr(UserAccount, "is_system_user")
        assert hasattr(UserAccount, "created_at")
        assert hasattr(UserAccount, "updated_at")


class TestUserGroupModel:
    """Tests for UserGroup model."""

    def test_table_name(self):
        """Test UserGroup table name."""
        from backend.persistence.models.operations import UserGroup

        assert UserGroup.__tablename__ == "user_groups"

    def test_columns_exist(self):
        """Test UserGroup has expected columns."""
        from backend.persistence.models.operations import UserGroup

        assert hasattr(UserGroup, "id")
        assert hasattr(UserGroup, "host_id")
        assert hasattr(UserGroup, "group_name")
        assert hasattr(UserGroup, "gid")
        assert hasattr(UserGroup, "security_id")
        assert hasattr(UserGroup, "is_system_group")
        assert hasattr(UserGroup, "created_at")
        assert hasattr(UserGroup, "updated_at")


class TestUserGroupMembershipModel:
    """Tests for UserGroupMembership model."""

    def test_table_name(self):
        """Test UserGroupMembership table name."""
        from backend.persistence.models.operations import UserGroupMembership

        assert UserGroupMembership.__tablename__ == "user_group_memberships"

    def test_columns_exist(self):
        """Test UserGroupMembership has expected columns."""
        from backend.persistence.models.operations import UserGroupMembership

        assert hasattr(UserGroupMembership, "id")
        assert hasattr(UserGroupMembership, "host_id")
        assert hasattr(UserGroupMembership, "user_account_id")
        assert hasattr(UserGroupMembership, "user_group_id")
        assert hasattr(UserGroupMembership, "created_at")
        assert hasattr(UserGroupMembership, "updated_at")


class TestUpdateExecutionLogModel:
    """Tests for UpdateExecutionLog model."""

    def test_table_name(self):
        """Test UpdateExecutionLog table name."""
        from backend.persistence.models.operations import UpdateExecutionLog

        assert UpdateExecutionLog.__tablename__ == "update_execution_log"

    def test_columns_exist(self):
        """Test UpdateExecutionLog has expected columns."""
        from backend.persistence.models.operations import UpdateExecutionLog

        assert hasattr(UpdateExecutionLog, "id")
        assert hasattr(UpdateExecutionLog, "host_id")
        assert hasattr(UpdateExecutionLog, "package_name")
        assert hasattr(UpdateExecutionLog, "from_version")
        assert hasattr(UpdateExecutionLog, "to_version")
        assert hasattr(UpdateExecutionLog, "package_manager")
        assert hasattr(UpdateExecutionLog, "execution_status")
        assert hasattr(UpdateExecutionLog, "started_at")
        assert hasattr(UpdateExecutionLog, "completed_at")
        assert hasattr(UpdateExecutionLog, "output_log")
        assert hasattr(UpdateExecutionLog, "error_log")
        assert hasattr(UpdateExecutionLog, "executed_by")
        assert hasattr(UpdateExecutionLog, "execution_method")
        assert hasattr(UpdateExecutionLog, "requires_reboot")
        assert hasattr(UpdateExecutionLog, "reboot_requested")
        assert hasattr(UpdateExecutionLog, "created_at")
        assert hasattr(UpdateExecutionLog, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import UpdateExecutionLog

        log = UpdateExecutionLog()
        log.id = uuid.uuid4()
        log.host_id = uuid.uuid4()
        log.package_name = "nginx"
        log.from_version = "1.18.0"
        log.to_version = "1.20.0"
        log.execution_status = "success"

        repr_str = repr(log)

        assert "UpdateExecutionLog" in repr_str
        assert "nginx" in repr_str
        assert "1.18.0" in repr_str
        assert "1.20.0" in repr_str
        assert "success" in repr_str


class TestMessageQueueModel:
    """Tests for MessageQueue model."""

    def test_table_name(self):
        """Test MessageQueue table name."""
        from backend.persistence.models.operations import MessageQueue

        assert MessageQueue.__tablename__ == "message_queue"

    def test_columns_exist(self):
        """Test MessageQueue has expected columns."""
        from backend.persistence.models.operations import MessageQueue

        assert hasattr(MessageQueue, "id")
        assert hasattr(MessageQueue, "host_id")
        assert hasattr(MessageQueue, "message_id")
        assert hasattr(MessageQueue, "direction")
        assert hasattr(MessageQueue, "message_type")
        assert hasattr(MessageQueue, "message_data")
        assert hasattr(MessageQueue, "status")
        assert hasattr(MessageQueue, "priority")
        assert hasattr(MessageQueue, "retry_count")
        assert hasattr(MessageQueue, "max_retries")
        assert hasattr(MessageQueue, "created_at")
        assert hasattr(MessageQueue, "scheduled_at")
        assert hasattr(MessageQueue, "started_at")
        assert hasattr(MessageQueue, "completed_at")
        assert hasattr(MessageQueue, "error_message")
        assert hasattr(MessageQueue, "last_error_at")
        assert hasattr(MessageQueue, "correlation_id")
        assert hasattr(MessageQueue, "reply_to")
        assert hasattr(MessageQueue, "expired_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import MessageQueue

        msg = MessageQueue()
        msg.id = uuid.uuid4()
        msg.host_id = uuid.uuid4()
        msg.message_id = "abc-123-def"
        msg.direction = "outbound"
        msg.message_type = "update_request"
        msg.status = "pending"
        msg.priority = "high"

        repr_str = repr(msg)

        assert "MessageQueue" in repr_str
        assert "abc-123-def" in repr_str
        assert "outbound" in repr_str
        assert "update_request" in repr_str
        assert "pending" in repr_str
        assert "high" in repr_str


class TestQueueMetricsModel:
    """Tests for QueueMetrics model."""

    def test_table_name(self):
        """Test QueueMetrics table name."""
        from backend.persistence.models.operations import QueueMetrics

        assert QueueMetrics.__tablename__ == "queue_metrics"

    def test_columns_exist(self):
        """Test QueueMetrics has expected columns."""
        from backend.persistence.models.operations import QueueMetrics

        assert hasattr(QueueMetrics, "id")
        assert hasattr(QueueMetrics, "queue_name")
        assert hasattr(QueueMetrics, "metric_type")
        assert hasattr(QueueMetrics, "metric_value")
        assert hasattr(QueueMetrics, "aggregation_period")
        assert hasattr(QueueMetrics, "period_start")
        assert hasattr(QueueMetrics, "period_end")
        assert hasattr(QueueMetrics, "sample_count")
        assert hasattr(QueueMetrics, "additional_data")
        assert hasattr(QueueMetrics, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import QueueMetrics

        metrics = QueueMetrics()
        metrics.id = uuid.uuid4()
        metrics.queue_name = "inbound"
        metrics.metric_type = "throughput"
        metrics.metric_value = "150.5"
        metrics.aggregation_period = "minute"

        repr_str = repr(metrics)

        assert "QueueMetrics" in repr_str
        assert "inbound" in repr_str
        assert "throughput" in repr_str
        assert "150.5" in repr_str
        assert "minute" in repr_str


class TestSavedScriptModel:
    """Tests for SavedScript model."""

    def test_table_name(self):
        """Test SavedScript table name."""
        from backend.persistence.models.operations import SavedScript

        assert SavedScript.__tablename__ == "saved_scripts"

    def test_columns_exist(self):
        """Test SavedScript has expected columns."""
        from backend.persistence.models.operations import SavedScript

        assert hasattr(SavedScript, "id")
        assert hasattr(SavedScript, "name")
        assert hasattr(SavedScript, "description")
        assert hasattr(SavedScript, "content")
        assert hasattr(SavedScript, "shell_type")
        assert hasattr(SavedScript, "platform")
        assert hasattr(SavedScript, "run_as_user")
        assert hasattr(SavedScript, "is_active")
        assert hasattr(SavedScript, "created_by")
        assert hasattr(SavedScript, "created_at")
        assert hasattr(SavedScript, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import SavedScript

        script = SavedScript()
        script.id = uuid.uuid4()
        script.name = "system_cleanup"
        script.shell_type = "bash"
        script.is_active = True

        repr_str = repr(script)

        assert "SavedScript" in repr_str
        assert "system_cleanup" in repr_str
        assert "bash" in repr_str
        assert "True" in repr_str


class TestScriptExecutionLogModel:
    """Tests for ScriptExecutionLog model."""

    def test_table_name(self):
        """Test ScriptExecutionLog table name."""
        from backend.persistence.models.operations import ScriptExecutionLog

        assert ScriptExecutionLog.__tablename__ == "script_execution_log"

    def test_columns_exist(self):
        """Test ScriptExecutionLog has expected columns."""
        from backend.persistence.models.operations import ScriptExecutionLog

        assert hasattr(ScriptExecutionLog, "id")
        assert hasattr(ScriptExecutionLog, "execution_id")
        assert hasattr(ScriptExecutionLog, "host_id")
        assert hasattr(ScriptExecutionLog, "saved_script_id")
        assert hasattr(ScriptExecutionLog, "script_name")
        assert hasattr(ScriptExecutionLog, "script_content")
        assert hasattr(ScriptExecutionLog, "shell_type")
        assert hasattr(ScriptExecutionLog, "run_as_user")
        assert hasattr(ScriptExecutionLog, "status")
        assert hasattr(ScriptExecutionLog, "requested_by")
        assert hasattr(ScriptExecutionLog, "started_at")
        assert hasattr(ScriptExecutionLog, "completed_at")
        assert hasattr(ScriptExecutionLog, "exit_code")
        assert hasattr(ScriptExecutionLog, "stdout_output")
        assert hasattr(ScriptExecutionLog, "stderr_output")
        assert hasattr(ScriptExecutionLog, "error_message")
        assert hasattr(ScriptExecutionLog, "created_at")
        assert hasattr(ScriptExecutionLog, "updated_at")
        assert hasattr(ScriptExecutionLog, "execution_uuid")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import ScriptExecutionLog

        log = ScriptExecutionLog()
        log.id = uuid.uuid4()
        log.execution_id = "exec-abc-123"
        log.status = "completed"
        log.host_id = uuid.uuid4()

        repr_str = repr(log)

        assert "ScriptExecutionLog" in repr_str
        assert "exec-abc-123" in repr_str
        assert "completed" in repr_str


class TestDiagnosticReportModel:
    """Tests for DiagnosticReport model."""

    def test_table_name(self):
        """Test DiagnosticReport table name."""
        from backend.persistence.models.operations import DiagnosticReport

        assert DiagnosticReport.__tablename__ == "diagnostic_report"

    def test_columns_exist(self):
        """Test DiagnosticReport has expected columns."""
        from backend.persistence.models.operations import DiagnosticReport

        assert hasattr(DiagnosticReport, "id")
        assert hasattr(DiagnosticReport, "collection_id")
        assert hasattr(DiagnosticReport, "host_id")
        assert hasattr(DiagnosticReport, "requested_by")
        assert hasattr(DiagnosticReport, "collection_status")
        assert hasattr(DiagnosticReport, "requested_at")
        assert hasattr(DiagnosticReport, "started_at")
        assert hasattr(DiagnosticReport, "completed_at")
        assert hasattr(DiagnosticReport, "collection_size_bytes")
        assert hasattr(DiagnosticReport, "files_collected")
        assert hasattr(DiagnosticReport, "error_message")
        assert hasattr(DiagnosticReport, "system_logs")
        assert hasattr(DiagnosticReport, "configuration_files")
        assert hasattr(DiagnosticReport, "process_list")
        assert hasattr(DiagnosticReport, "system_information")
        assert hasattr(DiagnosticReport, "network_information")
        assert hasattr(DiagnosticReport, "disk_usage")
        assert hasattr(DiagnosticReport, "environment_variables")
        assert hasattr(DiagnosticReport, "agent_logs")
        assert hasattr(DiagnosticReport, "created_at")
        assert hasattr(DiagnosticReport, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import DiagnosticReport

        report = DiagnosticReport()
        report.id = uuid.uuid4()
        report.collection_id = "diag-abc-123"
        report.collection_status = "completed"
        report.host_id = uuid.uuid4()

        repr_str = repr(report)

        assert "DiagnosticReport" in repr_str
        assert "diag-abc-123" in repr_str
        assert "completed" in repr_str


class TestTagModel:
    """Tests for Tag model."""

    def test_table_name(self):
        """Test Tag table name."""
        from backend.persistence.models.operations import Tag

        assert Tag.__tablename__ == "tags"

    def test_columns_exist(self):
        """Test Tag has expected columns."""
        from backend.persistence.models.operations import Tag

        assert hasattr(Tag, "id")
        assert hasattr(Tag, "name")
        assert hasattr(Tag, "description")
        assert hasattr(Tag, "created_at")
        assert hasattr(Tag, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import Tag

        tag = Tag()
        tag.id = uuid.uuid4()
        tag.name = "production"

        repr_str = repr(tag)

        assert "Tag" in repr_str
        assert "production" in repr_str


class TestHostTagModel:
    """Tests for HostTag model."""

    def test_table_name(self):
        """Test HostTag table name."""
        from backend.persistence.models.operations import HostTag

        assert HostTag.__tablename__ == "host_tags"

    def test_columns_exist(self):
        """Test HostTag has expected columns."""
        from backend.persistence.models.operations import HostTag

        assert hasattr(HostTag, "id")
        assert hasattr(HostTag, "host_id")
        assert hasattr(HostTag, "tag_id")
        assert hasattr(HostTag, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import HostTag

        host_tag = HostTag()
        host_tag.id = uuid.uuid4()
        host_tag.host_id = uuid.uuid4()
        host_tag.tag_id = uuid.uuid4()

        repr_str = repr(host_tag)

        assert "HostTag" in repr_str
        assert str(host_tag.host_id) in repr_str
        assert str(host_tag.tag_id) in repr_str


class TestPasswordResetTokenModel:
    """Tests for PasswordResetToken model."""

    def test_table_name(self):
        """Test PasswordResetToken table name."""
        from backend.persistence.models.operations import PasswordResetToken

        assert PasswordResetToken.__tablename__ == "password_reset_token"

    def test_columns_exist(self):
        """Test PasswordResetToken has expected columns."""
        from backend.persistence.models.operations import PasswordResetToken

        assert hasattr(PasswordResetToken, "id")
        assert hasattr(PasswordResetToken, "user_id")
        assert hasattr(PasswordResetToken, "token")
        assert hasattr(PasswordResetToken, "expires_at")
        assert hasattr(PasswordResetToken, "used_at")
        assert hasattr(PasswordResetToken, "created_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import PasswordResetToken

        token = PasswordResetToken()
        token.id = uuid.uuid4()
        token.user_id = uuid.uuid4()
        token.expires_at = datetime.now(timezone.utc)

        repr_str = repr(token)

        assert "PasswordResetToken" in repr_str
        assert str(token.user_id) in repr_str


class TestUbuntuProInfoModel:
    """Tests for UbuntuProInfo model."""

    def test_table_name(self):
        """Test UbuntuProInfo table name."""
        from backend.persistence.models.operations import UbuntuProInfo

        assert UbuntuProInfo.__tablename__ == "ubuntu_pro_info"

    def test_columns_exist(self):
        """Test UbuntuProInfo has expected columns."""
        from backend.persistence.models.operations import UbuntuProInfo

        assert hasattr(UbuntuProInfo, "id")
        assert hasattr(UbuntuProInfo, "host_id")
        assert hasattr(UbuntuProInfo, "attached")
        assert hasattr(UbuntuProInfo, "subscription_name")
        assert hasattr(UbuntuProInfo, "account_name")
        assert hasattr(UbuntuProInfo, "contract_name")
        assert hasattr(UbuntuProInfo, "tech_support_level")
        assert hasattr(UbuntuProInfo, "expires")
        assert hasattr(UbuntuProInfo, "created_at")
        assert hasattr(UbuntuProInfo, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import UbuntuProInfo

        info = UbuntuProInfo()
        info.id = uuid.uuid4()
        info.host_id = uuid.uuid4()
        info.attached = True

        repr_str = repr(info)

        assert "UbuntuProInfo" in repr_str
        assert "True" in repr_str


class TestUbuntuProServiceModel:
    """Tests for UbuntuProService model."""

    def test_table_name(self):
        """Test UbuntuProService table name."""
        from backend.persistence.models.operations import UbuntuProService

        assert UbuntuProService.__tablename__ == "ubuntu_pro_service"

    def test_columns_exist(self):
        """Test UbuntuProService has expected columns."""
        from backend.persistence.models.operations import UbuntuProService

        assert hasattr(UbuntuProService, "id")
        assert hasattr(UbuntuProService, "ubuntu_pro_info_id")
        assert hasattr(UbuntuProService, "service_name")
        assert hasattr(UbuntuProService, "entitled")
        assert hasattr(UbuntuProService, "status")
        assert hasattr(UbuntuProService, "created_at")
        assert hasattr(UbuntuProService, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import UbuntuProService

        service = UbuntuProService()
        service.id = uuid.uuid4()
        service.service_name = "esm-apps"
        service.entitled = "yes"
        service.status = "enabled"

        repr_str = repr(service)

        assert "UbuntuProService" in repr_str
        assert "esm-apps" in repr_str
        assert "yes" in repr_str
        assert "enabled" in repr_str


class TestUbuntuProSettingsModel:
    """Tests for UbuntuProSettings model."""

    def test_table_name(self):
        """Test UbuntuProSettings table name."""
        from backend.persistence.models.operations import UbuntuProSettings

        assert UbuntuProSettings.__tablename__ == "ubuntu_pro_settings"

    def test_columns_exist(self):
        """Test UbuntuProSettings has expected columns."""
        from backend.persistence.models.operations import UbuntuProSettings

        assert hasattr(UbuntuProSettings, "id")
        assert hasattr(UbuntuProSettings, "organization_name")
        assert hasattr(UbuntuProSettings, "master_key")
        assert hasattr(UbuntuProSettings, "auto_attach_enabled")
        assert hasattr(UbuntuProSettings, "created_at")
        assert hasattr(UbuntuProSettings, "updated_at")

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.operations import UbuntuProSettings

        settings = UbuntuProSettings()
        settings.id = uuid.uuid4()
        settings.organization_name = "Acme Corp"
        settings.auto_attach_enabled = True

        repr_str = repr(settings)

        assert "UbuntuProSettings" in repr_str
        assert "Acme Corp" in repr_str
        assert "True" in repr_str


class TestOperationsModuleConstants:
    """Tests for module constants."""

    def test_constants_exist(self):
        """Test module-level constants exist."""
        from backend.persistence.models.operations import HOST_ID_FK

        assert HOST_ID_FK == "host.id"
