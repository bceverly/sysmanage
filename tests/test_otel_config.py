"""
Tests for backend/telemetry/otel_config.py module.
Tests OpenTelemetry configuration and setup.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestIsTelemetryEnabled:
    """Tests for is_telemetry_enabled function."""

    @patch.dict(os.environ, {"OTEL_ENABLED": "true"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_enabled_when_env_true(self):
        """Test returns True when OTEL_ENABLED is true."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is True

    @patch.dict(os.environ, {"OTEL_ENABLED": "1"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_enabled_when_env_is_one(self):
        """Test returns True when OTEL_ENABLED is 1."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is True

    @patch.dict(os.environ, {"OTEL_ENABLED": "yes"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_enabled_when_env_yes(self):
        """Test returns True when OTEL_ENABLED is yes."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is True

    @patch.dict(os.environ, {"OTEL_ENABLED": "false"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_disabled_when_env_false(self):
        """Test returns False when OTEL_ENABLED is false."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is False

    @patch.dict(os.environ, {"OTEL_ENABLED": "0"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_disabled_when_env_zero(self):
        """Test returns False when OTEL_ENABLED is 0."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is False

    @patch.dict(os.environ, {}, clear=True)
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", True)
    def test_enabled_by_default(self):
        """Test returns True by default when env not set."""
        # Clear OTEL_ENABLED from env
        if "OTEL_ENABLED" in os.environ:
            del os.environ["OTEL_ENABLED"]

        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is True

    @patch.dict(os.environ, {"OTEL_ENABLED": "true"})
    @patch("backend.telemetry.otel_config.TELEMETRY_AVAILABLE", False)
    def test_disabled_when_packages_unavailable(self):
        """Test returns False when telemetry packages not available."""
        from backend.telemetry.otel_config import is_telemetry_enabled

        assert is_telemetry_enabled() is False


class TestSetupTelemetry:
    """Tests for setup_telemetry function."""

    @patch("backend.telemetry.otel_config.is_telemetry_enabled")
    def test_setup_does_nothing_when_disabled(self, mock_enabled):
        """Test setup returns early when telemetry disabled."""
        from backend.telemetry.otel_config import setup_telemetry

        mock_enabled.return_value = False
        mock_app = MagicMock()

        setup_telemetry(mock_app)

        # Should return without setting up anything


class TestGetTracer:
    """Tests for get_tracer function."""

    @patch("backend.telemetry.otel_config.trace", None)
    def test_get_tracer_returns_none_when_unavailable(self):
        """Test get_tracer returns None when trace module unavailable."""
        from backend.telemetry.otel_config import get_tracer

        result = get_tracer("test")

        assert result is None


class TestGetMeter:
    """Tests for get_meter function."""

    @patch("backend.telemetry.otel_config.metrics", None)
    def test_get_meter_returns_none_when_unavailable(self):
        """Test get_meter returns None when metrics module unavailable."""
        from backend.telemetry.otel_config import get_meter

        result = get_meter("test")

        assert result is None
