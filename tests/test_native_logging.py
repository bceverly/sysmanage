# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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

    def test_auto_resolves_via_platform_system(self):
        """target='auto' consults _auto_target when no system override given."""
        fake = MagicMock(spec=logging.Handler)
        with patch.object(
            native_logging.platform, "system", return_value="Linux"
        ), patch.object(native_logging, "_journald_handler", return_value=fake):
            handler = build_native_handler("auto", "ident")
        assert handler is fake

    def test_eventlog_dispatch(self):
        """target='eventlog' routes to _eventlog_handler."""
        fake = MagicMock(spec=logging.Handler)
        with patch.object(
            native_logging, "_eventlog_handler", return_value=fake
        ) as mock_fn:
            handler = build_native_handler("eventlog", "ident", system="Windows")
        assert handler is fake
        mock_fn.assert_called_once_with("ident", "Windows")

    def test_syslog_remote_dispatch(self):
        """syslog_remote routes to _syslog_remote_handler with the remote params."""
        fake = MagicMock(spec=logging.Handler)
        with patch.object(
            native_logging, "_syslog_remote_handler", return_value=fake
        ) as mock_fn:
            handler = build_native_handler(
                "syslog_remote",
                "ident",
                system="Linux",
                host="loghost",
                port=1514,
                facility="local0",
                protocol="tcp",
            )
        assert handler is fake
        mock_fn.assert_called_once_with("ident", "loghost", 1514, "local0", "tcp")


def _mock_syslog(return_value=None):
    """A SysLogHandler stand-in that preserves the real facility constants/dict.

    Patching the whole class with a bare MagicMock would turn ``LOG_USER`` and
    ``facility_names`` into mocks, so the handler's facility resolution couldn't
    be asserted.
    """
    real = logging.handlers.SysLogHandler
    mock = MagicMock(return_value=return_value)
    mock.LOG_USER = real.LOG_USER
    mock.facility_names = real.facility_names
    return mock


class TestSyslogRemoteHandler:
    """Tests for _syslog_remote_handler (Phase 14.5 remote forwarding)."""

    def test_no_host_returns_none(self):
        """Without a host there is nothing to forward to — no handler."""
        assert (
            native_logging._syslog_remote_handler("ident", None, 514, None, None)
            is None
        )
        assert (
            native_logging._syslog_remote_handler("ident", "", 514, None, None) is None
        )

    def test_udp_default(self):
        """A host with no protocol/port/facility → UDP, port 514, LOG_USER."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            handler = native_logging._syslog_remote_handler(
                "ident", "loghost", None, None, None
            )
        assert handler is fake
        kwargs = syslog_cls.call_args.kwargs
        assert kwargs["address"] == ("loghost", 514)
        assert kwargs["socktype"] == native_logging.socket.SOCK_DGRAM
        assert kwargs["facility"] == logging.handlers.SysLogHandler.LOG_USER
        fake.setFormatter.assert_called_once()

    def test_tcp_and_facility_and_port(self):
        """protocol=tcp → SOCK_STREAM; a named facility resolves; port honoured."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            native_logging._syslog_remote_handler(
                "ident", "loghost", 6514, "local3", "tcp"
            )
        kwargs = syslog_cls.call_args.kwargs
        assert kwargs["address"] == ("loghost", 6514)
        assert kwargs["socktype"] == native_logging.socket.SOCK_STREAM
        assert kwargs["facility"] == logging.handlers.SysLogHandler.LOG_LOCAL3

    def test_bad_facility_falls_back_to_user(self):
        """An unknown facility name falls back to LOG_USER rather than raising."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            native_logging._syslog_remote_handler(
                "ident", "loghost", 514, "not-a-facility", "udp"
            )
        assert (
            syslog_cls.call_args.kwargs["facility"]
            == logging.handlers.SysLogHandler.LOG_USER
        )

    def test_bad_port_falls_back_to_514(self):
        """A non-numeric port falls back to 514 instead of exploding."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            native_logging._syslog_remote_handler(
                "ident", "loghost", "not-a-number", None, None
            )
        assert syslog_cls.call_args.kwargs["address"] == ("loghost", 514)

    def test_socket_error_returns_none(self):
        """A failed TCP connect (OSError) yields None — file logging survives."""
        with patch.object(
            native_logging.logging.handlers,
            "SysLogHandler",
            side_effect=OSError("connection refused"),
        ):
            assert (
                native_logging._syslog_remote_handler(
                    "ident", "loghost", 514, None, "tcp"
                )
                is None
            )


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


class TestJournaldHandler:
    """_journald_handler: missing dep, construction failure, success."""

    def test_import_error_returns_none(self):
        """No python3-systemd installed → None (caller falls back)."""
        import builtins

        real_import = builtins.__import__

        def _fail(name, *args, **kwargs):
            if name.startswith("systemd"):
                raise ImportError("no systemd")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_fail):
            assert native_logging._journald_handler("ident") is None

    def test_construction_error_returns_none(self):
        """JournalHandler raising is swallowed → None."""
        import sys
        import types

        fake_mod = types.ModuleType("systemd.journal")
        fake_mod.JournalHandler = MagicMock(side_effect=RuntimeError("boom"))
        parent = types.ModuleType("systemd")
        with patch.dict(sys.modules, {"systemd": parent, "systemd.journal": fake_mod}):
            assert native_logging._journald_handler("ident") is None

    def test_success_returns_handler(self):
        """A working JournalHandler is returned as-is."""
        import sys
        import types

        fake = MagicMock(spec=logging.Handler)
        fake_mod = types.ModuleType("systemd.journal")
        fake_mod.JournalHandler = MagicMock(return_value=fake)
        parent = types.ModuleType("systemd")
        with patch.dict(sys.modules, {"systemd": parent, "systemd.journal": fake_mod}):
            assert native_logging._journald_handler("ident") is fake
        fake_mod.JournalHandler.assert_called_once_with(SYSLOG_IDENTIFIER="ident")


class TestSyslogHandler:
    """_syslog_handler: socket fallback + OSError handling."""

    def test_builds_with_local_socket(self):
        """When the syslog socket exists, the handler binds to it."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(
            native_logging.os.path, "exists", return_value=True
        ), patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            handler = native_logging._syslog_handler("ident", "Linux")
        assert handler is fake
        assert syslog_cls.call_args.kwargs["address"] == "/dev/log"
        fake.setFormatter.assert_called_once()

    def test_missing_socket_falls_back_to_udp(self):
        """A missing /dev/log falls back to the UDP localhost:514 tuple."""
        fake = MagicMock(spec=logging.Handler)
        syslog_cls = _mock_syslog(fake)
        with patch.object(
            native_logging.os.path, "exists", return_value=False
        ), patch.object(native_logging.logging.handlers, "SysLogHandler", syslog_cls):
            native_logging._syslog_handler("ident", "Linux")
        assert syslog_cls.call_args.kwargs["address"] == ("localhost", 514)

    def test_oserror_returns_none(self):
        """A socket bind failure yields None, keeping file logging alive."""
        with patch.object(
            native_logging.os.path, "exists", return_value=True
        ), patch.object(
            native_logging.logging.handlers,
            "SysLogHandler",
            side_effect=OSError("no socket"),
        ):
            assert native_logging._syslog_handler("ident", "Linux") is None


class TestEventlogHandlerSuccess:
    """_eventlog_handler happy path + construction failure on Windows."""

    def test_success_returns_handler(self):
        """A working NTEventLogHandler (with _welu) is returned."""
        good = MagicMock()
        good._welu = object()
        with patch.object(
            native_logging.logging.handlers,
            "NTEventLogHandler",
            return_value=good,
        ):
            assert native_logging._eventlog_handler("ident", "Windows") is good

    def test_construction_error_returns_none(self):
        """NTEventLogHandler raising is swallowed → None."""
        with patch.object(
            native_logging.logging.handlers,
            "NTEventLogHandler",
            side_effect=RuntimeError("no win32"),
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
