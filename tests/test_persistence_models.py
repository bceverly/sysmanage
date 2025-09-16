"""
Tests for persistence model __repr__ methods to achieve full coverage.
"""

from datetime import datetime, timezone

import pytest

from backend.persistence.models import (
    MessageQueue,
    QueueMetrics,
    SavedScript,
    ScriptExecutionLog,
    DiagnosticReport,
    Tag,
    HostTag,
    PasswordResetToken,
    UbuntuProInfo,
    UbuntuProService,
    UbuntuProSettings,
)


class TestModelReprMethods:
    """Test __repr__ methods for all persistence models."""

    def test_message_queue_repr(self):
        """Test MessageQueue __repr__ method (line 486)."""
        queue_item = MessageQueue(
            id=1,
            message_id="msg-123",
            message_type="test_type",
            direction="outbound",
            status="pending",
            host_id=42,
        )
        repr_str = repr(queue_item)
        assert "MessageQueue" in repr_str
        assert "msg-123" in repr_str
        assert "test_type" in repr_str
        assert "outbound" in repr_str
        assert "pending" in repr_str
        assert "42" in repr_str

    def test_queue_metrics_repr(self):
        """Test QueueMetrics __repr__ method (line 542)."""
        metrics = QueueMetrics(
            id=1,
            metric_name="test_metric",
            direction="inbound",
            count=100,
            host_id=24,
        )
        repr_str = repr(metrics)
        assert "QueueMetrics" in repr_str
        assert "test_metric" in repr_str
        assert "inbound" in repr_str
        assert "100" in repr_str
        assert "24" in repr_str

    def test_saved_script_repr(self):
        """Test SavedScript __repr__ method (line 573)."""
        script = SavedScript(
            name="test_script",
        )
        repr_str = repr(script)
        assert "SavedScript" in repr_str
        assert "test_script" in repr_str

    def test_script_execution_log_repr(self):
        """Test ScriptExecutionLog __repr__ method (line 624)."""
        log_entry = ScriptExecutionLog()
        repr_str = repr(log_entry)
        assert "ScriptExecutionLog" in repr_str

    def test_diagnostic_report_repr(self):
        """Test DiagnosticReport __repr__ method (line 680)."""
        report = DiagnosticReport()
        repr_str = repr(report)
        assert "DiagnosticReport" in repr_str

    def test_tag_repr(self):
        """Test Tag __repr__ method (line 706)."""
        tag = Tag(name="production")
        repr_str = repr(tag)
        assert "Tag" in repr_str
        assert "production" in repr_str

    def test_host_tag_repr(self):
        """Test HostTag __repr__ method (line 733)."""
        host_tag = HostTag()
        repr_str = repr(host_tag)
        assert "HostTag" in repr_str

    def test_password_reset_token_repr(self):
        """Test PasswordResetToken __repr__ method (line 758)."""
        token = PasswordResetToken()
        repr_str = repr(token)
        assert "PasswordResetToken" in repr_str

    def test_ubuntu_pro_info_repr(self):
        """Test UbuntuProInfo __repr__ method (line 796)."""
        pro_info = UbuntuProInfo()
        repr_str = repr(pro_info)
        assert "UbuntuProInfo" in repr_str

    def test_ubuntu_pro_service_repr(self):
        """Test UbuntuProService __repr__ method (line 830)."""
        service = UbuntuProService(name="esm-infra", status="enabled")
        repr_str = repr(service)
        assert "UbuntuProService" in repr_str
        assert "esm-infra" in repr_str
        assert "enabled" in repr_str

    def test_ubuntu_pro_settings_repr(self):
        """Test UbuntuProSettings __repr__ method (line 858)."""
        settings = UbuntuProSettings()
        repr_str = repr(settings)
        assert "UbuntuProSettings" in repr_str
