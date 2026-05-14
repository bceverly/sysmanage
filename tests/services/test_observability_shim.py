"""
Tests for backend.services.observability_shim — Phase 10.2 step 7 Phase D.

Covers the platform-detection mapping and the engine-first / legacy-fallback
contract used by ``/hosts/{host_id}/deploy-opentelemetry`` and
``/hosts/{host_id}/remove-opentelemetry``.

The shim itself is small (~150 lines) but underpins the cutover from the
agent's per-platform ``otel_deploy_*.py`` modules to the
``apply_deployment_plan`` engine path; locking its behaviour down keeps the
fallback contract honest as the engine evolves.
"""

# pylint: disable=protected-access,redefined-outer-name

from unittest.mock import MagicMock, patch

import pytest

from backend.services import observability_shim
from backend.services.observability_shim import (
    _detect_otel_platform,
    try_engine_graylog_attach,
    try_engine_otel_deploy,
    try_engine_otel_remove,
)


def _host(platform: str, host_id: str = "00000000-0000-0000-0000-000000000001"):
    """Build a Host-shaped MagicMock for the platform tests."""
    h = MagicMock()
    h.platform = platform
    h.id = host_id
    h.fqdn = "host.example"
    return h


def _db_with_pms(*managers):
    """Return a MagicMock db session whose SoftwarePackage query yields
    the given package_managers (one tuple per manager).

    The shim runs:
        db.query(SoftwarePackage.package_manager).filter(...).distinct().limit(8).all()
    so we replicate the chain through MagicMock.
    """
    db = MagicMock()
    chain = (
        db.query.return_value.filter.return_value.distinct.return_value.limit.return_value
    )
    chain.all.return_value = [(m,) for m in managers]
    return db


class TestDetectOtelPlatform:
    """``_detect_otel_platform`` maps host.platform + installed-PM sample
    to one of the engine's seven platform tokens, or None when the
    caller should fall back to the legacy WS command."""

    @pytest.mark.parametrize(
        ("platform_value", "expected"),
        [
            ("FreeBSD", "freebsd"),
            ("freebsd", "freebsd"),  # case-insensitive
            ("OpenBSD", "openbsd"),
            ("NetBSD", "netbsd"),
            ("Darwin", "macos"),
            ("Windows", "windows"),
        ],
    )
    def test_non_linux_platforms_map_directly(self, platform_value, expected):
        host = _host(platform_value)
        db = _db_with_pms()  # not consulted for non-Linux
        assert _detect_otel_platform(host, db) == expected

    def test_linux_with_apt_packages_is_linux_apt(self):
        host = _host("Linux")
        db = _db_with_pms("apt", "snap")
        assert _detect_otel_platform(host, db) == "linux_apt"

    def test_linux_with_dnf_is_linux_dnf(self):
        host = _host("Linux")
        db = _db_with_pms("dnf", "rpm")
        assert _detect_otel_platform(host, db) == "linux_dnf"

    def test_linux_with_yum_falls_back_to_linux_dnf(self):
        host = _host("Linux")
        db = _db_with_pms("yum")
        assert _detect_otel_platform(host, db) == "linux_dnf"

    def test_linux_with_no_inventory_returns_none(self):
        """Fresh host with no software inventory yet — engine can't tell
        apt from dnf, so the shim defers to the legacy detector."""
        host = _host("Linux")
        db = _db_with_pms()  # zero rows
        assert _detect_otel_platform(host, db) is None

    def test_linux_with_only_flatpak_returns_none(self):
        """Only universal package managers — no distro-specific signal."""
        host = _host("Linux")
        db = _db_with_pms("flatpak", "snap")
        assert _detect_otel_platform(host, db) is None

    def test_unknown_platform_returns_none(self):
        host = _host("Plan9")
        db = _db_with_pms()
        assert _detect_otel_platform(host, db) is None

    def test_empty_platform_returns_none(self):
        host = _host("")
        host.platform = None  # what a freshly-registered host looks like
        db = _db_with_pms()
        assert _detect_otel_platform(host, db) is None


class TestTryEngineOtelDeploy:
    """``try_engine_otel_deploy`` returns a queued message_id on success
    or None to signal "fall back to legacy"."""

    def test_returns_none_when_engine_not_loaded(self):
        host = _host("Linux")
        db = _db_with_pms("apt")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=None,
        ):
            assert try_engine_otel_deploy(host, "http://g:3000", db) is None

    def test_returns_none_when_engine_missing_builder(self):
        """Defensive: a wrong .so loaded as observability_engine that
        doesn't expose build_otel_multiplatform_deploy_plan must not
        crash — fall back to legacy."""
        bad_engine = MagicMock(spec=[])  # no attributes
        host = _host("Linux")
        db = _db_with_pms("apt")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=bad_engine,
        ):
            assert try_engine_otel_deploy(host, "http://g:3000", db) is None

    def test_returns_none_when_platform_undetectable(self):
        engine = MagicMock()
        host = _host("Linux")
        db = _db_with_pms()  # no installed packages -> linux can't be classified
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert try_engine_otel_deploy(host, "http://g:3000", db) is None

    def test_happy_path_calls_engine_and_enqueues(self):
        engine = MagicMock()
        engine.OtelMultiPlatformDeployRequest = MagicMock(return_value="REQ")
        engine.build_otel_multiplatform_deploy_plan = MagicMock(
            return_value={"plan": "FAKE"}
        )

        host = _host("Linux")
        db = _db_with_pms("apt")

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-123",
        ) as mock_enqueue:
            result = try_engine_otel_deploy(host, "http://g:3000", db)

        assert result == "msg-123"
        # Engine builder got the right platform token + grafana URL
        engine.OtelMultiPlatformDeployRequest.assert_called_once_with(
            platform="linux_apt",
            grafana_url="http://g:3000",
        )
        engine.build_otel_multiplatform_deploy_plan.assert_called_once_with("REQ")
        # Dispatcher got the plan + a generous install-timeout budget
        mock_enqueue.assert_called_once()
        _, kwargs = mock_enqueue.call_args
        assert kwargs["host_id"] == str(host.id)
        assert kwargs["plan"] == {"plan": "FAKE"}
        assert kwargs["timeout"] == 900  # apt/dnf install needs the headroom

    def test_engine_exception_falls_back_to_none(self):
        """If the engine's build_*_plan raises, return None so the
        caller uses its legacy path.  Never let the engine path break
        the user-visible endpoint."""
        engine = MagicMock()
        engine.OtelMultiPlatformDeployRequest = MagicMock(return_value="REQ")
        engine.build_otel_multiplatform_deploy_plan = MagicMock(
            side_effect=ValueError("bogus platform somehow")
        )

        host = _host("Linux")
        db = _db_with_pms("apt")

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-x",
        ) as mock_enqueue:
            result = try_engine_otel_deploy(host, "http://g:3000", db)

        assert result is None
        mock_enqueue.assert_not_called()


class TestTryEngineOtelRemove:
    """Symmetric coverage for the remove path."""

    def test_returns_none_when_engine_not_loaded(self):
        host = _host("Linux")
        db = _db_with_pms("apt")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=None,
        ):
            assert try_engine_otel_remove(host, db) is None

    def test_returns_none_when_engine_missing_remove_builder(self):
        engine = MagicMock(spec=["build_otel_multiplatform_deploy_plan"])
        # no build_otel_multiplatform_remove_plan attribute
        host = _host("Linux")
        db = _db_with_pms("apt")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert try_engine_otel_remove(host, db) is None

    def test_happy_path_dispatches_remove_plan(self):
        engine = MagicMock()
        engine.build_otel_multiplatform_remove_plan = MagicMock(
            return_value={"plan": "REMOVE"}
        )

        host = _host("FreeBSD")  # non-Linux path skips PM detection
        db = _db_with_pms()

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-rm",
        ) as mock_enqueue:
            result = try_engine_otel_remove(host, db)

        assert result == "msg-rm"
        engine.build_otel_multiplatform_remove_plan.assert_called_once_with("freebsd")
        _, kwargs = mock_enqueue.call_args
        assert kwargs["timeout"] == 600  # remove is faster than deploy


class TestTryEngineGraylogAttach:
    """``try_engine_graylog_attach`` — Phase 10.2 step 7 Graylog OSS shim.

    Same engine-first / legacy-fallback contract as the OTEL helpers:
    return a queued message_id on success, ``None`` on any miss so the
    caller's legacy WS ``ATTACH_TO_GRAYLOG`` path runs.
    """

    def _engine_with_graylog_builders(self):
        """Build a MagicMock engine that exposes the two builders the
        shim checks for plus the two request classes it instantiates."""
        engine = MagicMock()
        engine.GraylogRsyslogRequest = MagicMock(return_value="LINUX_REQ")
        engine.GraylogBsdSyslogAppendRequest = MagicMock(return_value="BSD_REQ")
        engine.build_graylog_linux_autodetect_plan = MagicMock(
            return_value={"plan": "LINUX"}
        )
        engine.build_graylog_bsd_syslog_append_plan = MagicMock(
            return_value={"plan": "BSD"}
        )
        return engine

    def test_returns_none_when_engine_not_loaded(self):
        host = _host("Linux")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=None,
        ):
            assert (
                try_engine_graylog_attach(host, "syslog_tcp", "g.example", 514)
                is None
            )

    def test_returns_none_when_engine_missing_linux_builder(self):
        """Defensive: an engine without ``build_graylog_linux_autodetect_plan``
        must not be invoked — fall back to legacy."""
        engine = MagicMock(spec=["build_graylog_bsd_syslog_append_plan"])
        host = _host("Linux")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert (
                try_engine_graylog_attach(host, "syslog_tcp", "g.example", 514)
                is None
            )

    def test_returns_none_when_engine_missing_bsd_builder(self):
        engine = MagicMock(spec=["build_graylog_linux_autodetect_plan"])
        host = _host("FreeBSD")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert (
                try_engine_graylog_attach(host, "syslog_tcp", "g.example", 514)
                is None
            )

    def test_returns_none_for_empty_platform(self):
        engine = self._engine_with_graylog_builders()
        host = _host("")
        host.platform = None
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert (
                try_engine_graylog_attach(host, "syslog_tcp", "g.example", 514)
                is None
            )

    def test_returns_none_for_unsupported_platform(self):
        """Windows sidecar attach requires api_token + node_id which the
        OSS endpoint payload doesn't carry, so the shim defers."""
        engine = self._engine_with_graylog_builders()
        host = _host("Windows")
        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ):
            assert (
                try_engine_graylog_attach(
                    host, "windows_sidecar", "g.example", 12201
                )
                is None
            )

    def test_linux_routes_to_autodetect_plan(self):
        engine = self._engine_with_graylog_builders()
        host = _host("Linux")

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-linux",
        ) as mock_enqueue:
            result = try_engine_graylog_attach(
                host, "syslog_tcp", "g.example.com", 514
            )

        assert result == "msg-linux"
        engine.GraylogRsyslogRequest.assert_called_once_with(
            graylog_server="g.example.com",
            port=514,
            mechanism="syslog_tcp",
        )
        engine.build_graylog_linux_autodetect_plan.assert_called_once_with("LINUX_REQ")
        engine.build_graylog_bsd_syslog_append_plan.assert_not_called()
        _, kwargs = mock_enqueue.call_args
        assert kwargs["host_id"] == str(host.id)
        assert kwargs["plan"] == {"plan": "LINUX"}
        assert kwargs["timeout"] == 600

    @pytest.mark.parametrize(
        ("platform_value", "expected_variant"),
        [
            ("FreeBSD", "freebsd"),
            ("OpenBSD", "openbsd"),
            ("NetBSD", "netbsd"),
        ],
    )
    def test_bsd_routes_to_append_plan_with_correct_variant(
        self, platform_value, expected_variant
    ):
        engine = self._engine_with_graylog_builders()
        host = _host(platform_value)

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-bsd",
        ):
            result = try_engine_graylog_attach(
                host, "syslog_udp", "g.example.com", 1514
            )

        assert result == "msg-bsd"
        engine.GraylogBsdSyslogAppendRequest.assert_called_once_with(
            graylog_server="g.example.com",
            port=1514,
            mechanism="syslog_udp",
            bsd_variant=expected_variant,
        )
        engine.build_graylog_bsd_syslog_append_plan.assert_called_once_with("BSD_REQ")
        engine.build_graylog_linux_autodetect_plan.assert_not_called()

    def test_engine_exception_falls_back_to_none(self):
        engine = self._engine_with_graylog_builders()
        engine.build_graylog_linux_autodetect_plan.side_effect = ValueError("boom")

        host = _host("Linux")

        with patch.object(
            observability_shim.module_loader,
            "get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan",
            return_value="msg-x",
        ) as mock_enqueue:
            result = try_engine_graylog_attach(
                host, "syslog_tcp", "g.example.com", 514
            )

        assert result is None
        mock_enqueue.assert_not_called()
