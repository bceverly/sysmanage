"""
Tests for backend/persistence/models/graylog_integration.py module.
Tests GraylogIntegrationSettings model structure and methods.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestGraylogIntegrationSettingsModel:
    """Tests for GraylogIntegrationSettings model."""

    def test_table_name(self):
        """Test GraylogIntegrationSettings table name."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        assert (
            GraylogIntegrationSettings.__tablename__ == "graylog_integration_settings"
        )

    def test_columns_exist(self):
        """Test GraylogIntegrationSettings has expected columns."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        assert hasattr(GraylogIntegrationSettings, "id")
        assert hasattr(GraylogIntegrationSettings, "enabled")
        assert hasattr(GraylogIntegrationSettings, "host_id")
        assert hasattr(GraylogIntegrationSettings, "manual_url")
        assert hasattr(GraylogIntegrationSettings, "use_managed_server")
        assert hasattr(GraylogIntegrationSettings, "api_token_vault_token")
        assert hasattr(GraylogIntegrationSettings, "has_gelf_tcp")
        assert hasattr(GraylogIntegrationSettings, "gelf_tcp_port")
        assert hasattr(GraylogIntegrationSettings, "has_syslog_tcp")
        assert hasattr(GraylogIntegrationSettings, "syslog_tcp_port")
        assert hasattr(GraylogIntegrationSettings, "has_syslog_udp")
        assert hasattr(GraylogIntegrationSettings, "syslog_udp_port")
        assert hasattr(GraylogIntegrationSettings, "has_windows_sidecar")
        assert hasattr(GraylogIntegrationSettings, "windows_sidecar_port")
        assert hasattr(GraylogIntegrationSettings, "inputs_last_checked")


class TestGraylogIntegrationRepr:
    """Tests for GraylogIntegrationSettings __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.enabled = True
        settings.host_id = uuid.uuid4()

        repr_str = repr(settings)

        assert "GraylogIntegrationSettings" in repr_str
        assert "enabled=True" in repr_str


class TestGraylogIntegrationToDict:
    """Tests for GraylogIntegrationSettings.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all expected fields."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.enabled = True
        settings.host_id = uuid.uuid4()
        settings.manual_url = "http://graylog.example.com:9000"
        settings.use_managed_server = False
        settings.api_token_vault_token = "vault:token:123"
        settings.has_gelf_tcp = True
        settings.gelf_tcp_port = 12201
        settings.has_syslog_tcp = True
        settings.syslog_tcp_port = 514
        settings.has_syslog_udp = True
        settings.syslog_udp_port = 514
        settings.has_windows_sidecar = False
        settings.windows_sidecar_port = None
        settings.inputs_last_checked = datetime.now(timezone.utc)
        settings.created_at = datetime.now(timezone.utc)
        settings.updated_at = datetime.now(timezone.utc)
        settings.host = None

        result = settings.to_dict()

        assert result["enabled"] is True
        assert result["manual_url"] == "http://graylog.example.com:9000"
        assert result["use_managed_server"] is False
        assert result["api_token"] == "***"
        assert result["has_gelf_tcp"] is True
        assert result["gelf_tcp_port"] == 12201
        assert result["has_syslog_tcp"] is True
        assert result["syslog_tcp_port"] == 514
        assert result["has_syslog_udp"] is True
        assert result["syslog_udp_port"] == 514
        assert result["has_windows_sidecar"] is False
        assert result["windows_sidecar_port"] is None

    def test_to_dict_hides_api_token(self):
        """Test to_dict masks API token."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.enabled = True
        settings.api_token_vault_token = "secret_token"
        settings.host = None

        result = settings.to_dict()

        assert result["api_token"] == "***"
        assert "secret_token" not in str(result)

    def test_to_dict_none_api_token(self):
        """Test to_dict when API token is None."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.enabled = False
        settings.api_token_vault_token = None
        settings.host = None

        result = settings.to_dict()

        assert result["api_token"] is None

    def test_to_dict_with_host(self):
        """Test to_dict includes host when present."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.enabled = True

        # Mock host with required attributes
        mock_host = MagicMock()
        mock_host.id = uuid.uuid4()
        mock_host.fqdn = "graylog-server.example.com"
        mock_host.ipv4 = "192.168.1.100"
        mock_host.ipv6 = None
        mock_host.platform = "linux"
        mock_host.active = True
        mock_host.approval_status = "approved"
        settings.host = mock_host

        result = settings.to_dict()

        assert result["host"] is not None
        assert result["host"]["fqdn"] == "graylog-server.example.com"
        assert result["host"]["ipv4"] == "192.168.1.100"
        assert result["host"]["platform"] == "linux"
        assert result["host"]["active"] is True

    def test_to_dict_none_host_id(self):
        """Test to_dict when host_id is None."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.host_id = None
        settings.host = None

        result = settings.to_dict()

        assert result["host_id"] is None

    def test_to_dict_none_inputs_last_checked(self):
        """Test to_dict when inputs_last_checked is None."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.id = uuid.uuid4()
        settings.inputs_last_checked = None
        settings.host = None

        result = settings.to_dict()

        assert result["inputs_last_checked"] is None


class TestGraylogIntegrationGraylogUrl:
    """Tests for GraylogIntegrationSettings.graylog_url property."""

    def test_graylog_url_managed_server(self):
        """Test graylog_url returns managed server URL."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.use_managed_server = True

        mock_host = MagicMock()
        mock_host.fqdn = "graylog.example.com"
        settings.host = mock_host

        assert settings.graylog_url == "http://graylog.example.com:9000"

    def test_graylog_url_manual_url(self):
        """Test graylog_url returns manual URL when not using managed server."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.use_managed_server = False
        settings.manual_url = "https://my-graylog.example.com:8080"
        settings.host = None

        assert settings.graylog_url == "https://my-graylog.example.com:8080"

    def test_graylog_url_none_when_not_configured(self):
        """Test graylog_url returns None when not properly configured."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.use_managed_server = True
        settings.host = None

        assert settings.graylog_url is None

    def test_graylog_url_none_when_manual_not_set(self):
        """Test graylog_url returns None when manual URL not set."""
        from backend.persistence.models.graylog_integration import (
            GraylogIntegrationSettings,
        )

        settings = GraylogIntegrationSettings()
        settings.use_managed_server = False
        settings.manual_url = None

        assert settings.graylog_url is None
