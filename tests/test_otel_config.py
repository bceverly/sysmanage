# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend/telemetry/otel_config.py module.
Tests OpenTelemetry configuration and setup.
"""

import os
from unittest.mock import MagicMock, patch


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


class TestOtlpExporterIsIndependentlyOptional:
    """The OTLP exporters must be optional SEPARATELY from the rest of the stack.

    opentelemetry-exporter-otlp pulls grpcio, a compiled package with no build on
    some platforms; the OpenBSD port omits it deliberately (see
    installer/openbsd/build-libs.sh).  These imports used to live in the same try
    block as the API, SDK, instrumentation and Prometheus exporter, so that one
    missing optional exporter silently disabled ALL telemetry -- Prometheus
    metrics and every instrumentation went dark on a platform where those
    packages were installed and working.  If someone merges the two try blocks
    again, these tests fail.
    """

    def test_core_telemetry_survives_missing_otlp_exporter(self):
        """Blocking opentelemetry.exporter.otlp must not disable telemetry."""
        import importlib
        import sys

        blocked = "opentelemetry.exporter.otlp"

        class _Blocker:
            def find_spec(self, name, path=None, target=None):
                if name.startswith(blocked):
                    raise ImportError("simulated: %s not installed" % name)
                return None

        saved_modules = {
            name: mod
            for name, mod in sys.modules.items()
            if name.startswith(blocked) or name.startswith("backend.telemetry")
        }
        blocker = _Blocker()
        sys.meta_path.insert(0, blocker)
        try:
            for name in list(sys.modules):
                if name.startswith(blocked) or name.startswith("backend.telemetry"):
                    del sys.modules[name]
            cfg = importlib.import_module("backend.telemetry.otel_config")

            # The whole point: core telemetry stays up ...
            assert cfg.TELEMETRY_AVAILABLE is True
            # ... and only OTLP is marked unavailable.
            assert cfg.OTLP_AVAILABLE is False
            # The Prometheus exporter and instrumentation must still be usable.
            assert cfg.PrometheusMetricReader is not None
            assert cfg.FastAPIInstrumentor is not None
            assert cfg.SQLAlchemyInstrumentor is not None
        finally:
            sys.meta_path.remove(blocker)
            for name in list(sys.modules):
                if name.startswith(blocked) or name.startswith("backend.telemetry"):
                    del sys.modules[name]
            sys.modules.update(saved_modules)
            importlib.import_module("backend.telemetry.otel_config")

    def test_otlp_available_when_exporter_present(self):
        """Sanity check the flag is not just hardcoded False."""
        from backend.telemetry import otel_config

        assert otel_config.OTLP_AVAILABLE is True
