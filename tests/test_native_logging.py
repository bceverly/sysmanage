"""Tests for platform-native log handler selection + server wiring (Phase 13.3)."""

# pylint: disable=protected-access

import logging
from unittest.mock import MagicMock, patch

from backend.utils import native_logging
from backend.utils.native_logging import build_native_handler


class TestAutoTarget:
    """Tests for _auto_target platform mapping."""

    def test_linux_journald(self):
        """Linux defaults to journald."""
        assert native_logging._auto_target("Linux") == "journald"

    def test_windows_eventlog(self):
        """Windows defaults to the Event Log."""
        assert native_logging._auto_target("Windows") == "eventlog"

    def test_darwin_and_bsd_syslog(self):
        """macOS and the BSDs default to syslog."""
        assert native_logging._auto_target("Darwin") == "syslog"
        assert native_logging._auto_target("NetBSD") == "syslog"


class TestSyslogAddress:
    """Tests for _syslog_address per platform."""

    def test_addresses(self):
        """Each platform maps to its syslog socket."""
        assert native_logging._syslog_address("Linux") == "/dev/log"
        assert native_logging._syslog_address("Darwin") == "/var/run/syslog"
        assert native_logging._syslog_address("FreeBSD") == "/dev/log"
        assert native_logging._syslog_address("Plan9") == ("localhost", 514)


class TestBuildNativeHandler:
    """Tests for build_native_handler dispatch + fallbacks."""

    def test_none_target(self):
        """An explicit none/off target yields no handler."""
        assert build_native_handler("none") is None
        assert build_native_handler("off") is None

    def test_syslog(self):
        """syslog target builds via _syslog_handler."""
        fake = MagicMock(spec=logging.Handler)
        with patch.object(
            native_logging, "_syslog_handler", return_value=fake
        ) as mock_fn:
            handler = build_native_handler("syslog", "ident", system="Linux")
        assert handler is fake
        mock_fn.assert_called_once_with("ident", "Linux")

    def test_journald_falls_back_to_syslog(self):
        """When journald is unavailable, the Linux path falls back to syslog."""
        fake_syslog = MagicMock(spec=logging.Handler)
        with patch.object(
            native_logging, "_journald_handler", return_value=None
        ), patch.object(native_logging, "_syslog_handler", return_value=fake_syslog):
            handler = build_native_handler("journald", "ident", system="Linux")
        assert handler is fake_syslog

    def test_unknown_target(self):
        """An unrecognised target yields no handler."""
        assert build_native_handler("smoke-signals", system="Linux") is None


class TestEventlogGuard:
    """_eventlog_handler must never return a degraded off-Windows handler."""

    def test_off_windows_returns_none(self):
        """Off-Windows, no Event Log handler is created."""
        assert native_logging._eventlog_handler("ident", "Linux") is None

    def test_degraded_handler_rejected(self):
        """A pywin32-less NTEventLogHandler (no _welu) is rejected."""
        degraded = MagicMock()
        degraded._welu = None
        with patch.object(
            native_logging.logging.handlers,
            "NTEventLogHandler",
            return_value=degraded,
        ):
            assert native_logging._eventlog_handler("ident", "Windows") is None


class TestMaybeAddNativeHandler:
    """Tests for the server's configure_logging wiring helper."""

    def test_disabled_adds_nothing(self):
        """With logging.native off, no native handler is attached."""
        from backend.startup import logging_config

        with patch(
            "backend.config.config.get_config",
            return_value={"logging": {"native": False}},
        ), patch.object(logging_config, "build_native_handler") as build_m:
            logging_config._maybe_add_native_handler()
        build_m.assert_not_called()

    def test_enabled_attaches_handler(self):
        """With logging.native on, the resolved handler is attached to root."""
        from backend.startup import logging_config

        fake = MagicMock(spec=logging.Handler)
        with patch(
            "backend.config.config.get_config",
            return_value={"logging": {"native": True, "native_target": "syslog"}},
        ), patch.object(
            logging_config, "build_native_handler", return_value=fake
        ) as build_m, patch.object(
            logging_config.logging.root, "addHandler"
        ) as add_m:
            logging_config._maybe_add_native_handler()
        build_m.assert_called_once_with(target="syslog", identifier="sysmanage")
        add_m.assert_called_once_with(fake)
