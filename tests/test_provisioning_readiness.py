# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the Phase 18.2 S1 provisioning-readiness preflight (OSS half).

Two halves:
  * ``ProvisioningReadiness`` role logic — which tool combinations satisfy
    which provisioning role, what to offer installing, and the own-DHCP vs
    proxyDHCP recommendation.  This is the gate that decides whether PXE may
    be attempted at all.
  * ``provisioning_result_handlers`` — parsing the agent probe's stdout and
    upserting the row.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring,protected-access

from unittest.mock import MagicMock, patch

from backend.persistence.models.provisioning import ProvisioningReadiness
from backend.services import provisioning_result_handlers as prh

# ---------------------------------------------------------------------------
# Role readiness
# ---------------------------------------------------------------------------


def _row(tools=None, services=None):
    row = ProvisioningReadiness(host_id="h1")
    row.tools = tools or {}
    row.services = services or {}
    return row


class TestRoleReadiness:
    def test_dnsmasq_alone_satisfies_dhcp_and_tftp(self):
        """The property that makes dnsmasq the recommended stack — one package
        covers both roles (exactly what libvirt's own dnsmasq did in the S0
        spike)."""
        row = _row({"dnsmasq": "present"})
        assert row.is_ready_for("dhcp")
        assert row.is_ready_for("tftp")

    def test_alternative_groups_satisfy_a_role(self):
        assert _row({"dhcpd": "present"}).is_ready_for("dhcp")
        assert _row({"kea-dhcp4": "present"}).is_ready_for("dhcp")
        assert _row({"atftpd": "present"}).is_ready_for("tftp")
        assert _row({"httpd": "present"}).is_ready_for("http")
        assert _row({"ipxe.efi": "present"}).is_ready_for("boot")

    def test_missing_tool_fails_the_role(self):
        row = _row({"dnsmasq": "missing", "dhcpd": "missing"})
        assert not row.is_ready_for("dhcp")

    def test_unknown_role_is_never_ready(self):
        assert not _row({"dnsmasq": "present"}).is_ready_for("telepathy")
        assert not _row({"dnsmasq": "present"}).is_ready_for("")

    def test_is_ready_requires_every_role(self):
        partial = _row({"dnsmasq": "present"})
        assert not partial.is_ready()
        full = _row(
            {
                "dnsmasq": "present",
                "nginx": "present",
                "pxelinux.0": "present",
            }
        )
        assert full.is_ready()

    def test_non_dict_tools_is_not_ready(self):
        """A row whose probe never landed must gate PXE, not pass it."""
        row = _row()
        row.tools = None
        assert not row.is_ready_for("dhcp")
        assert not row.is_ready()


class TestMissingFor:
    def test_offers_the_cheapest_group(self):
        """A host that already has dnsmasq must not be told to install
        isc-dhcp-server."""
        row = _row({"dnsmasq": "missing", "dhcpd": "missing"})
        assert row.missing_for("dhcp") == ["dnsmasq"]

    def test_satisfied_role_needs_nothing(self):
        assert _row({"dnsmasq": "present"}).missing_for("dhcp") == []

    def test_unknown_role_needs_nothing(self):
        assert _row().missing_for("nope") == []


class TestDhcpModeRecommendation:
    def test_existing_dhcp_server_forces_proxy(self):
        """The safety property: never recommend a second authoritative DHCP
        server onto a segment that already has one."""
        row = _row(services={"dhcp_port_67": "in_use"})
        assert row.recommended_dhcp_mode() == "proxy"

    def test_free_port_allows_own(self):
        assert _row(services={"dhcp_port_67": "free"}).recommended_dhcp_mode() == "own"

    def test_unknown_defaults_to_own(self):
        assert (
            _row(services={"dhcp_port_67": "unknown"}).recommended_dhcp_mode() == "own"
        )
        assert _row().recommended_dhcp_mode() == "own"


class TestToDict:
    def test_shape(self):
        row = _row({"dnsmasq": "present"}, {"dhcp_port_67": "in_use"})
        out = row.to_dict()
        assert out["host_id"] == "h1"
        assert out["ready"] is False
        assert out["roles"]["dhcp"] == {"ready": True, "missing": []}
        assert out["roles"]["http"]["ready"] is False
        assert out["roles"]["http"]["missing"] == ["nginx"]
        assert out["recommended_dhcp_mode"] == "proxy"
        for key in ("install_status", "apply_status", "last_check_message_id"):
            assert key in out


# ---------------------------------------------------------------------------
# Probe stdout parsing
# ---------------------------------------------------------------------------


class TestParsePreflightStdout:
    def test_splits_tools_from_listeners(self):
        out = prh._parse_preflight_stdout(
            "dnsmasq=present\n"
            "nginx=missing\n"
            "pxelinux.0=present\n"
            "dhcp_port_67=in_use\n"
            "tftp_port_69=free\n"
            "platform=Linux\n"
            "distro=ubuntu\n"
        )
        assert out["tools"] == {
            "dnsmasq": "present",
            "nginx": "missing",
            "pxelinux.0": "present",
        }
        assert out["services"] == {
            "dhcp_port_67": "in_use",
            "tftp_port_69": "free",
        }
        assert out["platform"] == "Linux"
        assert out["distro"] == "ubuntu"

    def test_ignores_blank_and_malformed_lines(self):
        out = prh._parse_preflight_stdout("\n  \nnot-a-pair\ndnsmasq=present\n")
        assert out["tools"] == {"dnsmasq": "present"}

    def test_ignores_unrecognised_values(self):
        """A probe from a different engine version must not poison the row."""
        out = prh._parse_preflight_stdout("dnsmasq=perhaps\nnginx=present\n")
        assert out["tools"] == {"nginx": "present"}

    def test_empty_stdout(self):
        out = prh._parse_preflight_stdout("")
        assert out == {
            "tools": {},
            "services": {},
            "platform": None,
            "distro": None,
        }

    def test_truncates_long_platform_and_distro(self):
        out = prh._parse_preflight_stdout(
            "platform=%s\ndistro=%s\n" % ("x" * 80, "y" * 80)
        )
        assert len(out["platform"]) == 40
        assert len(out["distro"]) == 40


# ---------------------------------------------------------------------------
# Result handlers
# ---------------------------------------------------------------------------


def _outcome(status="succeeded", stdout="", stderr="", error=""):
    return {"status": status, "stdout": stdout, "stderr": stderr, "error": error}


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_a, **_kw):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """Returns a preset row per model class; records what was added."""

    def __init__(self, rows=None):
        self._rows = rows or {}
        self.added = []
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._rows.get(model))

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


class TestPreflightHandler:
    def test_upserts_and_clears_inflight_marker(self):
        row = _row()
        row.last_check_message_id = "msg-1"
        session = _FakeSession({ProvisioningReadiness: row})
        with patch.object(prh, "_stamp_firewall_flavor"):
            prh._apply_provisioning_preflight(
                session, "h1", _outcome(stdout="dnsmasq=present\ndhcp_port_67=free\n")
            )
        assert row.tools == {"dnsmasq": "present"}
        assert row.services == {"dhcp_port_67": "free"}
        assert row.last_check_message_id is None
        assert row.last_check_error is None
        assert row.last_check_at is not None

    def test_creates_row_when_absent(self):
        session = _FakeSession({ProvisioningReadiness: None})
        with patch.object(prh, "_stamp_firewall_flavor"):
            prh._apply_provisioning_preflight(
                session, "h1", _outcome(stdout="nginx=present\n")
            )
        assert len(session.added) == 1

    def test_failed_probe_records_error(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        prh._apply_provisioning_preflight(
            session, "h1", _outcome(status="failed", stderr="boom")
        )
        assert row.last_check_error == "boom"
        assert row.last_check_message_id is None

    def test_failed_probe_does_not_stamp_firewall_flavor(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        with patch.object(prh, "_stamp_firewall_flavor") as stamp:
            prh._apply_provisioning_preflight(session, "h1", _outcome(status="failed"))
        stamp.assert_not_called()


class TestFirewallFlavorStamp:
    def test_stamps_from_host_platform(self):
        host = MagicMock(platform="linux", platform_release="ubuntu 24.04")
        row = _row()
        session = _FakeSession()
        session.query = lambda model: _FakeQuery(host)
        prh._stamp_firewall_flavor(session, row, "h1")
        assert row.firewall_flavor == "ufw"

    def test_missing_host_leaves_flavor_untouched(self):
        row = _row()
        row.firewall_flavor = "firewalld"
        session = _FakeSession()
        session.query = lambda model: _FakeQuery(None)
        prh._stamp_firewall_flavor(session, row, "h1")
        assert row.firewall_flavor == "firewalld"


class TestInstallAndApplyHandlers:
    def test_install_success(self):
        row = _row()
        row.last_install_message_id = "msg-2"
        session = _FakeSession({ProvisioningReadiness: row})
        prh._apply_provisioning_install(session, "h1", _outcome())
        assert row.install_status == "succeeded"
        assert row.last_install_message_id is None
        assert row.last_install_error is None

    def test_install_failure(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        prh._apply_provisioning_install(
            session, "h1", _outcome(status="failed", error="no such package")
        )
        assert row.install_status == "failed"
        assert row.last_install_error == "no such package"

    def test_apply_success_and_failure(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        prh._apply_provisioning_apply(session, "h1", _outcome())
        assert row.apply_status == "succeeded"
        prh._apply_provisioning_apply(
            session, "h1", _outcome(status="failed", stderr="dnsmasq refused to start")
        )
        assert row.apply_status == "failed"
        assert row.last_apply_error == "dnsmasq refused to start"


class TestOpResultRouting:
    def test_unknown_action_is_dropped_loudly(self, caplog):
        with patch.object(prh.db, "get_session_local") as gsl:
            prh._apply_provisioning_op_result("provisioning_teleport", "h1", _outcome())
            gsl.assert_not_called()
        assert "Unknown provisioning_op action" in caplog.text

    def test_known_action_commits(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        session_local = MagicMock()
        session_local.return_value.__enter__ = lambda _s: session
        session_local.return_value.__exit__ = lambda *_a: False
        with patch.object(prh.db, "get_session_local", return_value=session_local):
            prh._apply_provisioning_op_result(
                "provisioning_apply", "h1", _outcome(status="failed", stderr="x")
            )
        assert session.committed
        assert row.apply_status == "failed"

    def test_successful_install_chains_a_followup_probe(self):
        """Without the auto-probe the card would show stale tool presence."""
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        session_local = MagicMock()
        session_local.return_value.__enter__ = lambda _s: session
        session_local.return_value.__exit__ = lambda *_a: False
        with patch.object(
            prh.db, "get_session_local", return_value=session_local
        ), patch.object(prh, "_queue_followup_preflight") as followup:
            prh._apply_provisioning_op_result("provisioning_install", "h1", _outcome())
        followup.assert_called_once()

    def test_failed_install_does_not_chain(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        session_local = MagicMock()
        session_local.return_value.__enter__ = lambda _s: session
        session_local.return_value.__exit__ = lambda *_a: False
        with patch.object(
            prh.db, "get_session_local", return_value=session_local
        ), patch.object(prh, "_queue_followup_preflight") as followup:
            prh._apply_provisioning_op_result(
                "provisioning_install", "h1", _outcome(status="failed")
            )
        followup.assert_not_called()


class TestFollowupProbe:
    def test_stamps_message_id_so_polling_continues(self):
        row = _row()
        session = _FakeSession({ProvisioningReadiness: row})
        session_local = MagicMock()
        session_local.return_value.__enter__ = lambda _s: session
        session_local.return_value.__exit__ = lambda *_a: False
        engine = MagicMock()
        engine.build_provisioning_preflight_plan.return_value = {"action": "x"}
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=engine,
        ), patch(
            "backend.services.proplus_dispatch.enqueue_apply_plan", return_value="msg-9"
        ) as enqueue, patch(
            "backend.services.proplus_dispatch._register_correlation"
        ) as reg:
            prh._queue_followup_preflight("h1", session_local)
        enqueue.assert_called_once()
        reg.assert_called_once_with(
            "msg-9", "provisioning_op", "provisioning_preflight", "h1"
        )
        assert row.last_check_message_id == "msg-9"

    def test_unloaded_engine_is_logged_not_raised(self, caplog):
        session_local = MagicMock()
        with patch(
            "backend.licensing.module_loader.module_loader.get_module",
            return_value=None,
        ):
            prh._queue_followup_preflight("h1", session_local)
        assert "no longer loaded" in caplog.text
