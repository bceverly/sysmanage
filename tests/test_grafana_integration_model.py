"""
Tests for backend/persistence/models/grafana_integration.py module.
Tests GrafanaIntegrationSettings model structure and methods.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestGrafanaIntegrationSettingsModel:
    """Tests for GrafanaIntegrationSettings model."""

    def test_table_name(self):
        """Test GrafanaIntegrationSettings table name."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        assert (
            GrafanaIntegrationSettings.__tablename__ == "grafana_integration_settings"
        )

    def test_columns_exist(self):
        """Test GrafanaIntegrationSettings has expected columns."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        assert hasattr(GrafanaIntegrationSettings, "id")
        assert hasattr(GrafanaIntegrationSettings, "enabled")
        assert hasattr(GrafanaIntegrationSettings, "host_id")
        assert hasattr(GrafanaIntegrationSettings, "manual_url")
        assert hasattr(GrafanaIntegrationSettings, "use_managed_server")
        assert hasattr(GrafanaIntegrationSettings, "api_key_vault_token")
        assert hasattr(GrafanaIntegrationSettings, "created_at")
        assert hasattr(GrafanaIntegrationSettings, "updated_at")


class TestGrafanaIntegrationRepr:
    """Tests for GrafanaIntegrationSettings __repr__ method."""

    def test_repr_format(self):
        """Test __repr__ returns expected format."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.id = 1
        settings.enabled = True
        settings.host_id = uuid.uuid4()

        repr_str = repr(settings)

        assert "GrafanaIntegrationSettings" in repr_str
        assert "enabled=True" in repr_str


class TestGrafanaIntegrationToDict:
    """Tests for GrafanaIntegrationSettings.to_dict method."""

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all expected fields."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.id = 1
        settings.enabled = True
        settings.host_id = uuid.uuid4()
        settings.manual_url = "http://grafana.example.com:3000"
        settings.use_managed_server = False
        settings.api_key_vault_token = "vault:token:123"
        settings.created_at = datetime.now(timezone.utc)
        settings.updated_at = datetime.now(timezone.utc)
        settings.host = None

        result = settings.to_dict()

        assert result["id"] == 1
        assert result["enabled"] is True
        assert result["manual_url"] == "http://grafana.example.com:3000"
        assert result["use_managed_server"] is False
        # API key should be masked
        assert result["api_key"] == "***"

    def test_to_dict_hides_api_key(self):
        """Test to_dict masks API key."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.id = 1
        settings.enabled = True
        settings.api_key_vault_token = "secret_token"
        settings.host = None

        result = settings.to_dict()

        assert result["api_key"] == "***"
        assert "secret_token" not in str(result)

    def test_to_dict_none_api_key(self):
        """Test to_dict when API key is None."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.id = 1
        settings.enabled = False
        settings.api_key_vault_token = None
        settings.host = None

        result = settings.to_dict()

        assert result["api_key"] is None

    def test_to_dict_with_host(self):
        """Test to_dict includes host when present."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.id = 1
        settings.enabled = True

        # Mock host with to_dict method
        mock_host = MagicMock()
        mock_host.to_dict.return_value = {"hostname": "grafana-server"}
        settings.host = mock_host

        result = settings.to_dict()

        assert result["host"] == {"hostname": "grafana-server"}


class TestGrafanaIntegrationGrafanaUrl:
    """Tests for GrafanaIntegrationSettings.grafana_url property."""

    def test_grafana_url_managed_server(self):
        """Test grafana_url returns managed server URL."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.use_managed_server = True

        # Mock host with fqdn
        mock_host = MagicMock()
        mock_host.fqdn = "grafana.example.com"
        settings.host = mock_host

        assert settings.grafana_url == "http://grafana.example.com:3000"

    def test_grafana_url_manual_url(self):
        """Test grafana_url returns manual URL when not using managed server."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.use_managed_server = False
        settings.manual_url = "https://my-grafana.example.com:8080"
        settings.host = None

        assert settings.grafana_url == "https://my-grafana.example.com:8080"

    def test_grafana_url_none_when_not_configured(self):
        """Test grafana_url returns None when not properly configured."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.use_managed_server = True
        settings.host = None  # No host configured

        assert settings.grafana_url is None

    def test_grafana_url_none_when_manual_not_set(self):
        """Test grafana_url returns None when manual URL not set."""
        from backend.persistence.models.grafana_integration import (
            GrafanaIntegrationSettings,
        )

        settings = GrafanaIntegrationSettings()
        settings.use_managed_server = False
        settings.manual_url = None

        assert settings.grafana_url is None
