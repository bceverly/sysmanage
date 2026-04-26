"""
Tests for backend.api.firewall_roles_helpers.

These exercise the pure helper layer (Pydantic validators, port shaping,
status-table mutation, response serialization) without touching FastAPI
routing. The route handler tests live elsewhere; this file's job is to
catch regressions in the validation rules and JSON-state surgery.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.api.firewall_roles_helpers import (
    COMMON_PORTS,
    FirewallRoleCreate,
    FirewallRoleUpdate,
    HostFirewallRoleCreate,
    PortCreate,
    PortResponse,
    get_host_firewall_ports,
    get_role_ports,
    queue_apply_firewall_roles,
    queue_remove_firewall_ports,
    role_to_response_dict,
    update_firewall_status_remove_ports,
)

# ---------------------------------------------------------------------------
# COMMON_PORTS sanity
# ---------------------------------------------------------------------------


class TestCommonPortsConstant:
    def test_includes_well_known_services(self):
        names = {p["name"] for p in COMMON_PORTS}
        assert {"SSH", "HTTP", "HTTPS", "DNS", "PostgreSQL"} <= names

    def test_every_entry_has_required_keys(self):
        for entry in COMMON_PORTS:
            assert {"port", "name", "default_protocol"} <= entry.keys()
            assert 0 <= entry["port"] <= 65535
            assert entry["default_protocol"] in {"tcp", "udp", "both"}


# ---------------------------------------------------------------------------
# PortCreate validation
# ---------------------------------------------------------------------------


class TestPortCreateValidation:
    def test_default_construct_is_tcp_ipv4_ipv6(self):
        p = PortCreate(port_number=22)
        assert p.tcp is True and p.udp is False
        assert p.ipv4 is True and p.ipv6 is True

    def test_port_zero_is_allowed(self):
        # 0 means "any port" per the docstring.
        p = PortCreate(port_number=0)
        assert p.port_number == 0

    def test_port_negative_rejected(self):
        with pytest.raises(ValidationError):
            PortCreate(port_number=-1)

    def test_port_above_max_rejected(self):
        with pytest.raises(ValidationError):
            PortCreate(port_number=70000)

    def test_must_pick_at_least_one_protocol(self):
        with pytest.raises(ValidationError, match="protocol"):
            PortCreate(port_number=80, tcp=False, udp=False)

    def test_must_pick_at_least_one_ip_version(self):
        with pytest.raises(ValidationError, match="IP version"):
            PortCreate(port_number=80, ipv4=False, ipv6=False)

    def test_udp_only_is_fine(self):
        p = PortCreate(port_number=53, tcp=False, udp=True)
        assert p.tcp is False and p.udp is True


# ---------------------------------------------------------------------------
# FirewallRoleCreate / FirewallRoleUpdate name validation
# ---------------------------------------------------------------------------


class TestRoleCreateValidation:
    def test_strips_whitespace(self):
        r = FirewallRoleCreate(name="   web tier   ")
        assert r.name == "web tier"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            FirewallRoleCreate(name="")

    def test_rejects_whitespace_only_name(self):
        with pytest.raises(ValidationError):
            FirewallRoleCreate(name="   ")

    def test_rejects_overlong_name(self):
        with pytest.raises(ValidationError, match="100 characters"):
            FirewallRoleCreate(name="x" * 101)

    def test_accepts_max_length(self):
        FirewallRoleCreate(name="x" * 100)


class TestRoleUpdateValidation:
    def test_none_name_allowed(self):
        r = FirewallRoleUpdate(name=None)
        assert r.name is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            FirewallRoleUpdate(name="   ")

    def test_overlong_name_rejected(self):
        with pytest.raises(ValidationError):
            FirewallRoleUpdate(name="x" * 101)


class TestHostFirewallRoleCreate:
    def test_round_trip(self):
        m = HostFirewallRoleCreate(firewall_role_id="abc-123")
        assert m.firewall_role_id == "abc-123"


# ---------------------------------------------------------------------------
# PortResponse / FirewallRoleResponse — UUID coercion
# ---------------------------------------------------------------------------


class TestResponseUuidCoercion:
    def test_uuid_object_becomes_string(self):
        import uuid

        u = uuid.uuid4()
        resp = PortResponse(
            id=u, port_number=22, tcp=True, udp=False, ipv4=True, ipv6=True
        )
        assert resp.id == str(u)

    def test_already_string_passes_through(self):
        resp = PortResponse(
            id="abc", port_number=80, tcp=True, udp=False, ipv4=True, ipv6=True
        )
        assert resp.id == "abc"


# ---------------------------------------------------------------------------
# get_role_ports — pure data shaping
# ---------------------------------------------------------------------------


def _port(port_number, tcp=True, udp=False, ipv4=True, ipv6=True):
    return MagicMock(port_number=port_number, tcp=tcp, udp=udp, ipv4=ipv4, ipv6=ipv6)


class TestGetRolePorts:
    def test_role_with_no_ports_returns_empty(self):
        role = MagicMock(open_ports=[])
        assert get_role_ports(role) == {"ipv4_ports": [], "ipv6_ports": []}

    def test_ipv4_only_port_is_only_in_ipv4_list(self):
        role = MagicMock(open_ports=[_port(22, ipv4=True, ipv6=False)])
        out = get_role_ports(role)
        assert out["ipv4_ports"] == [{"port": 22, "tcp": True, "udp": False}]
        assert out["ipv6_ports"] == []

    def test_ipv6_only_port_is_only_in_ipv6_list(self):
        role = MagicMock(open_ports=[_port(22, ipv4=False, ipv6=True)])
        out = get_role_ports(role)
        assert out["ipv4_ports"] == []
        assert out["ipv6_ports"] == [{"port": 22, "tcp": True, "udp": False}]

    def test_dual_stack_port_is_in_both_lists(self):
        role = MagicMock(open_ports=[_port(443, tcp=True, udp=False)])
        out = get_role_ports(role)
        assert {"port": 443, "tcp": True, "udp": False} in out["ipv4_ports"]
        assert {"port": 443, "tcp": True, "udp": False} in out["ipv6_ports"]


# ---------------------------------------------------------------------------
# get_host_firewall_ports — across multiple role assignments
# ---------------------------------------------------------------------------


class TestGetHostFirewallPorts:
    def test_aggregates_across_assignments_dedups(self):
        # Two role assignments that share port 22 (IPv4+IPv6 dual-stack).
        role_a = MagicMock(open_ports=[_port(22)])  # tcp ipv4+ipv6
        role_b = MagicMock(open_ports=[_port(22), _port(80)])  # 22 dup + 80 new
        assignment_a = MagicMock(firewall_role=role_a)
        assignment_b = MagicMock(firewall_role=role_b)

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            assignment_a,
            assignment_b,
        ]

        out = get_host_firewall_ports(db, "host-id")
        # Dedup means port 22 appears only once.
        assert out["ipv4_ports"].count({"port": 22, "tcp": True, "udp": False}) == 1
        assert {"port": 80, "tcp": True, "udp": False} in out["ipv4_ports"]

    def test_assignment_with_missing_role_is_skipped(self):
        # If the relationship resolved to None (deleted role), the helper
        # silently skips it rather than crashing.
        assignment = MagicMock(firewall_role=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [assignment]
        assert get_host_firewall_ports(db, "h") == {
            "ipv4_ports": [],
            "ipv6_ports": [],
        }


# ---------------------------------------------------------------------------
# queue_apply_firewall_roles / queue_remove_firewall_ports
# ---------------------------------------------------------------------------


class TestQueueApplyFirewallRoles:
    def test_builds_plan_and_enqueues(self):
        host = MagicMock(
            id="host-uuid",
            fqdn="h.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
            platform_version="x",
        )
        db = MagicMock()
        # No assignments → empty port lists.
        db.query.return_value.filter.return_value.all.return_value = []

        with patch(
            "backend.api.firewall_roles_helpers.firewall_plan_builder.build_apply_role_ports_plan",
            return_value={"plan": "x"},
        ) as build, patch("backend.api.firewall_roles_helpers.queue_ops") as qops:
            queue_apply_firewall_roles(db, host)

        build.assert_called_once()
        qops.enqueue_message.assert_called_once()
        call_kwargs = qops.enqueue_message.call_args.kwargs
        assert call_kwargs["host_id"] == "host-uuid"
        assert call_kwargs["direction"] == "outbound"


class TestQueueRemoveFirewallPorts:
    def test_passes_ports_to_remove_to_planner(self):
        host = MagicMock(
            id="hid",
            fqdn="h.example",
            platform="Linux",
            platform_release="Ubuntu 24.04",
            platform_version="x",
        )
        db = MagicMock()
        ports_to_remove = {
            "ipv4_ports": [{"port": 22, "tcp": True, "udp": False}],
            "ipv6_ports": [],
        }
        with patch(
            "backend.api.firewall_roles_helpers.firewall_plan_builder.build_remove_role_ports_plan",
            return_value={"plan": "y"},
        ) as build, patch("backend.api.firewall_roles_helpers.queue_ops") as qops:
            queue_remove_firewall_ports(db, host, ports_to_remove)
        # The planner should receive the host info dict + both port lists.
        args, _ = build.call_args
        assert args[1] == ports_to_remove["ipv4_ports"]
        assert args[2] == ports_to_remove["ipv6_ports"]
        qops.enqueue_message.assert_called_once()


# ---------------------------------------------------------------------------
# update_firewall_status_remove_ports — JSON filtering surgery
# ---------------------------------------------------------------------------


def _firewall_status_row(ipv4_json=None, ipv6_json=None):
    row = MagicMock()
    row.ipv4_ports = ipv4_json
    row.ipv6_ports = ipv6_json
    return row


class TestUpdateFirewallStatusRemovePorts:
    def test_no_status_row_is_noop(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        # Should return without raising.
        update_firewall_status_remove_ports(
            db, "h", {"ipv4_ports": [], "ipv6_ports": []}
        )

    def test_removes_protocol_keeps_port_with_other_protocol(self):
        # Initial state: port 80 supports tcp + udp; we remove tcp.
        row = _firewall_status_row(
            ipv4_json=json.dumps([{"port": "80", "protocols": ["tcp", "udp"]}]),
            ipv6_json=None,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        update_firewall_status_remove_ports(
            db,
            "h",
            {
                "ipv4_ports": [{"port": 80, "tcp": True, "udp": False}],
                "ipv6_ports": [],
            },
        )

        remaining = json.loads(row.ipv4_ports)
        assert remaining == [{"port": "80", "protocols": ["udp"]}]

    def test_removes_last_protocol_drops_the_port_entirely(self):
        row = _firewall_status_row(
            ipv4_json=json.dumps([{"port": "22", "protocols": ["tcp"]}])
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        update_firewall_status_remove_ports(
            db,
            "h",
            {
                "ipv4_ports": [{"port": 22, "tcp": True, "udp": False}],
                "ipv6_ports": [],
            },
        )

        # All protocols stripped → ipv4_ports field is reset to None.
        assert row.ipv4_ports is None

    def test_handles_ipv6_independently(self):
        row = _firewall_status_row(
            ipv4_json=json.dumps([{"port": "80", "protocols": ["tcp"]}]),
            ipv6_json=json.dumps([{"port": "80", "protocols": ["tcp"]}]),
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        update_firewall_status_remove_ports(
            db,
            "h",
            {
                "ipv4_ports": [],
                # Remove only the IPv6 instance.
                "ipv6_ports": [{"port": 80, "tcp": True, "udp": False}],
            },
        )

        # IPv4 untouched.
        assert json.loads(row.ipv4_ports) == [{"port": "80", "protocols": ["tcp"]}]
        assert row.ipv6_ports is None

    def test_malformed_ipv4_json_logs_and_skips_field(self):
        # If ipv4_ports somehow has invalid JSON, the helper must not raise.
        row = _firewall_status_row(ipv4_json="<<not json>>")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row

        # No exception — and the bad field is left alone.
        update_firewall_status_remove_ports(
            db, "h", {"ipv4_ports": [], "ipv6_ports": []}
        )
        assert row.ipv4_ports == "<<not json>>"

    def test_malformed_ipv6_json_logs_and_skips_field(self):
        row = _firewall_status_row(ipv6_json="<<not json>>")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        update_firewall_status_remove_ports(
            db, "h", {"ipv4_ports": [], "ipv6_ports": []}
        )
        assert row.ipv6_ports == "<<not json>>"


# ---------------------------------------------------------------------------
# role_to_response_dict
# ---------------------------------------------------------------------------


class TestRoleToResponseDict:
    def test_serializes_basic_fields(self):
        import uuid as _uuid
        from datetime import datetime, timezone

        rid = _uuid.uuid4()
        cb = _uuid.uuid4()
        port = MagicMock(
            id=_uuid.uuid4(),
            port_number=22,
            tcp=True,
            udp=False,
            ipv4=True,
            ipv6=True,
        )

        # Use a plain object instead of MagicMock so `.name` is a real string
        # (MagicMock auto-creates a .name attribute that breaks the assertion).
        class _Role:
            pass

        role = _Role()
        role.id = rid
        role.name = "web"
        role.created_at = datetime.now(timezone.utc)
        role.created_by = cb
        role.updated_at = None
        role.updated_by = None
        role.open_ports = [port]
        out = role_to_response_dict(role)
        assert out["id"] == str(rid)
        assert out["name"] == "web"
        assert out["created_by"] == str(cb)
        assert out["updated_at"] is None
        assert out["updated_by"] is None
        assert out["open_ports"][0]["port_number"] == 22

    def test_handles_none_audit_fields(self):
        class _Role:
            pass

        role = _Role()
        role.id = "rid"
        role.name = "empty"
        role.created_at = None
        role.created_by = None
        role.updated_at = None
        role.updated_by = None
        role.open_ports = []
        out = role_to_response_dict(role)
        assert out["created_by"] is None
        assert out["updated_by"] is None
        assert out["open_ports"] == []
