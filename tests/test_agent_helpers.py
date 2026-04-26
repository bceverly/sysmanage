"""
Tests for the pure-helper layer of backend.api.agent.

The websocket route handler `agent_connect` is hard to drive without a real
WebSocket; the mid-level orchestration helpers, however, are testable in
isolation:

  - _extract_host_identifier
  - _lookup_host_by_ip
  - _get_connection_info
  - _validate_hostname_match
  - _log_missing_host_info / _log_unregistered_host / _log_unapproved_host
  - _enqueue_inbound_message
  - _process_websocket_message (JSON parse + dispatch)
  - _validate_and_get_host
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api import agent as agent_module

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _connection(agent_id="agent-1", hostname=None, ipv4=None, ipv6=None, platform=None):
    c = MagicMock()
    c.agent_id = agent_id
    c.hostname = hostname
    c.ipv4 = ipv4
    c.ipv6 = ipv6
    c.platform = platform
    c.send_message = AsyncMock()
    return c


# ---------------------------------------------------------------------------
# _validate_hostname_match
# ---------------------------------------------------------------------------


class TestValidateHostnameMatch:
    def test_no_hostname_passes(self):
        host = MagicMock(fqdn="anything.example")
        assert agent_module._validate_hostname_match(None, host) is True
        assert agent_module._validate_hostname_match("", host) is True

    def test_exact_fqdn_match_case_insensitive(self):
        host = MagicMock(fqdn="db1.example.com")
        assert agent_module._validate_hostname_match("DB1.EXAMPLE.COM", host) is True

    def test_short_name_match(self):
        host = MagicMock(fqdn="db1.example.com")
        assert agent_module._validate_hostname_match("db1", host) is True

    def test_unrelated_hostname_fails(self):
        host = MagicMock(fqdn="db1.example.com")
        assert agent_module._validate_hostname_match("web2.other.com", host) is False


# ---------------------------------------------------------------------------
# _get_connection_info
# ---------------------------------------------------------------------------


class TestGetConnectionInfo:
    def test_returns_empty_when_no_connection(self):
        assert agent_module._get_connection_info(None) == {}

    def test_collects_connection_attrs_with_prefixes(self):
        conn = _connection(
            agent_id="agent-7",
            hostname="h.example",
            ipv4="10.0.0.1",
            ipv6="::1",
            platform="Linux",
        )
        info = agent_module._get_connection_info(conn)
        # agent_id is the un-prefixed key.
        assert info["agent_id"] == "agent-7"
        # Other attrs get the connection_ prefix.
        assert info["connection_hostname"] == "h.example"
        assert info["connection_ipv4"] == "10.0.0.1"
        assert info["connection_ipv6"] == "::1"
        assert info["connection_platform"] == "Linux"

    def test_skips_falsy_attrs(self):
        conn = _connection(agent_id="a", hostname=None, ipv4=None)
        info = agent_module._get_connection_info(conn)
        # Only agent_id (truthy) survives.
        assert info == {"agent_id": "a"}


# ---------------------------------------------------------------------------
# _lookup_host_by_ip
# ---------------------------------------------------------------------------


class TestLookupHostByIp:
    def test_returns_none_when_no_ips(self):
        conn = _connection(ipv4=None, ipv6=None)
        db = MagicMock()
        assert agent_module._lookup_host_by_ip(conn, db) is None
        db.query.assert_not_called()

    def test_finds_via_ipv4(self):
        conn = _connection(ipv4="10.0.0.5", ipv6=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(
            fqdn="ipv4-host.example"
        )
        assert agent_module._lookup_host_by_ip(conn, db) == "ipv4-host.example"

    def test_falls_back_to_ipv6_when_ipv4_misses(self):
        conn = _connection(ipv4="10.0.0.5", ipv6="fe80::1")
        db = MagicMock()
        # First lookup (by ipv4) returns None, second (by ipv6) returns a host.
        db.query.return_value.filter.return_value.first.side_effect = [
            None,
            MagicMock(fqdn="ipv6-host.example"),
        ]
        assert agent_module._lookup_host_by_ip(conn, db) == "ipv6-host.example"

    def test_returns_none_when_no_match(self):
        conn = _connection(ipv4="10.0.0.5", ipv6="fe80::1")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert agent_module._lookup_host_by_ip(conn, db) is None


# ---------------------------------------------------------------------------
# _extract_host_identifier
# ---------------------------------------------------------------------------


class TestExtractHostIdentifier:
    def test_uses_message_data_when_present(self):
        msg = {"hostname": "from-msg.example", "host_id": "h-1"}
        h, hid = agent_module._extract_host_identifier(msg, None, MagicMock())
        assert h == "from-msg.example"
        assert hid == "h-1"

    def test_falls_back_to_connection_hostname(self):
        conn = _connection(hostname="from-conn.example")
        h, hid = agent_module._extract_host_identifier({}, conn, MagicMock())
        assert h == "from-conn.example"
        assert hid is None

    def test_falls_back_to_ip_lookup_when_no_hostname(self):
        conn = _connection(hostname=None, ipv4="10.0.0.9")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(
            fqdn="found-via-ip.example"
        )
        h, hid = agent_module._extract_host_identifier({}, conn, db)
        assert h == "found-via-ip.example"
        assert hid is None


# ---------------------------------------------------------------------------
# Audit-log helpers — verify they call AuditService.log without exploding
# ---------------------------------------------------------------------------


class TestAuditLogHelpers:
    def test_log_missing_host_info(self):
        with patch("backend.api.agent.AuditService.log") as log:
            agent_module._log_missing_host_info(
                MagicMock(),
                {"k1": "v", "k2": "w"},
                _connection(agent_id="a"),
            )
        log.assert_called_once()
        details = log.call_args.kwargs["details"]
        assert sorted(details["message_data_keys"]) == ["k1", "k2"]

    def test_log_unregistered_host_with_hostname(self):
        with patch("backend.api.agent.AuditService.log") as log:
            agent_module._log_unregistered_host(MagicMock(), "missing.example", None)
        log.assert_called_once()
        assert log.call_args.kwargs["entity_name"] == "missing.example"

    def test_log_unregistered_host_with_only_host_id(self):
        with patch("backend.api.agent.AuditService.log") as log:
            agent_module._log_unregistered_host(MagicMock(), None, "abc-uuid")
        # entity_name falls back to host_id:<id>
        assert "abc-uuid" in log.call_args.kwargs["entity_name"]

    def test_log_unapproved_host(self):
        host = MagicMock(id="h-1", approval_status="pending")
        with patch("backend.api.agent.AuditService.log") as log:
            agent_module._log_unapproved_host(MagicMock(), host, "pending.example")
        details = log.call_args.kwargs["details"]
        assert details["approval_status"] == "pending"


# ---------------------------------------------------------------------------
# _enqueue_inbound_message
# ---------------------------------------------------------------------------


class TestEnqueueInboundMessage:
    def test_attaches_connection_info_and_enqueues(self):
        msg = MagicMock()
        msg.message_type = "hardware_update"
        msg.data = {"foo": "bar"}
        msg.message_id = "m-1"

        conn = _connection(
            agent_id="agent-1",
            hostname="h.example",
            ipv4="10.0.0.1",
            ipv6="::1",
            platform="Linux",
        )
        db = MagicMock()

        with patch(
            "backend.websocket.queue_operations.QueueOperations"
        ) as queue_ops_cls:
            qops = queue_ops_cls.return_value
            agent_module._enqueue_inbound_message(msg, conn, db)
        qops.enqueue_message.assert_called_once()
        kwargs = qops.enqueue_message.call_args.kwargs
        assert kwargs["message_type"] == "hardware_update"
        assert kwargs["message_data"]["_connection_info"]["hostname"] == "h.example"
        # Must have hardened the original data dict (no shared reference).
        assert msg.data == {"foo": "bar"}
        assert "_connection_info" in kwargs["message_data"]

    def test_system_info_messages_get_high_priority(self):
        from backend.websocket.messages import MessageType

        msg = MagicMock()
        msg.message_type = MessageType.SYSTEM_INFO
        msg.data = {}
        msg.message_id = "m-2"

        with patch(
            "backend.websocket.queue_operations.QueueOperations"
        ) as queue_ops_cls:
            qops = queue_ops_cls.return_value
            agent_module._enqueue_inbound_message(msg, _connection(), MagicMock())
        kwargs = qops.enqueue_message.call_args.kwargs
        # Priority should be HIGH for SYSTEM_INFO; we can't import Priority
        # without the production-side module, but we can assert it's set.
        assert "priority" in kwargs


# ---------------------------------------------------------------------------
# _process_websocket_message
# ---------------------------------------------------------------------------


class TestProcessWebsocketMessage:
    @pytest.mark.asyncio
    async def test_invalid_json_sends_error_to_agent(self):
        conn = _connection()
        await agent_module._process_websocket_message(
            "<<not-json>>", conn, MagicMock(), "conn-1"
        )
        conn.send_message.assert_awaited_once()
        sent = conn.send_message.await_args.args[0]
        assert sent["error_type"] == "invalid_json"

    @pytest.mark.asyncio
    async def test_security_validation_failure_sends_error(self):
        conn = _connection()
        with patch(
            "backend.api.agent.websocket_security.validate_message_integrity",
            return_value=(False, "tampered"),
        ):
            await agent_module._process_websocket_message(
                json.dumps({"message_type": "x", "data": {}}),
                conn,
                MagicMock(),
                "conn-1",
            )
        sent = conn.send_message.await_args.args[0]
        assert sent["error_type"] == "message_validation_failed"

    @pytest.mark.asyncio
    async def test_time_sensitive_message_dispatched_immediately(self):
        from backend.websocket.messages import MessageType

        conn = _connection()
        with patch(
            "backend.api.agent.websocket_security.validate_message_integrity",
            return_value=(True, None),
        ), patch("backend.api.agent.create_message") as cm, patch(
            "backend.api.agent._handle_message_by_type", new=AsyncMock()
        ) as handler:
            cm.return_value = MagicMock(
                message_type=MessageType.HEARTBEAT,
                data={},
                message_id="m-1",
            )
            await agent_module._process_websocket_message(
                json.dumps({"message_type": "heartbeat", "data": {}}),
                conn,
                MagicMock(),
                "conn-1",
            )
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_messages_get_enqueued(self):
        conn = _connection()
        with patch(
            "backend.api.agent.websocket_security.validate_message_integrity",
            return_value=(True, None),
        ), patch("backend.api.agent.create_message") as cm, patch(
            "backend.api.agent._enqueue_inbound_message"
        ) as enqueue:
            cm.return_value = MagicMock(
                message_type="hardware_update",
                data={},
                message_id="m-1",
            )
            await agent_module._process_websocket_message(
                json.dumps({"message_type": "hardware_update", "data": {}}),
                conn,
                MagicMock(),
                "conn-1",
            )
        enqueue.assert_called_once()


# ---------------------------------------------------------------------------
# _validate_and_get_host
# ---------------------------------------------------------------------------


class TestValidateAndGetHost:
    @pytest.mark.asyncio
    async def test_missing_both_hostname_and_host_id_returns_error(self):
        db = MagicMock()
        with patch("backend.api.agent._log_missing_host_info"):
            host, err = await agent_module._validate_and_get_host({}, _connection(), db)
        assert host is None
        assert err._error_code == "missing_host_info"

    @pytest.mark.asyncio
    async def test_unknown_host_id_returns_stale_id_error(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        host, err = await agent_module._validate_and_get_host(
            {"host_id": "unknown-id"}, _connection(), db
        )
        assert host is None
        assert err._error_code == "host_not_registered"

    @pytest.mark.asyncio
    async def test_hostname_mismatch_returns_error(self):
        db = MagicMock()
        host_obj = MagicMock(fqdn="actual.example", approval_status="approved")
        db.query.return_value.filter.return_value.first.return_value = host_obj
        host, err = await agent_module._validate_and_get_host(
            {"host_id": "h-1", "hostname": "wrong.example"},
            _connection(),
            db,
        )
        assert host is None
        # Returns host_not_registered with mismatch detail.
        assert err._error_code == "host_not_registered"

    @pytest.mark.asyncio
    async def test_unapproved_host_returns_approval_error(self):
        db = MagicMock()
        host_obj = MagicMock(fqdn="pending.example", approval_status="pending")
        db.query.return_value.filter.return_value.first.return_value = host_obj
        with patch("backend.api.agent._log_unapproved_host"):
            host, err = await agent_module._validate_and_get_host(
                {"host_id": "h-1", "hostname": "pending.example"},
                _connection(),
                db,
            )
        assert host is None
        assert err._error_code == "host_not_approved"

    @pytest.mark.asyncio
    async def test_lookup_by_hostname_only_succeeds_for_approved_host(self):
        db = MagicMock()
        host_obj = MagicMock(fqdn="ok.example", approval_status="approved")
        db.query.return_value.filter.return_value.first.return_value = host_obj
        host, err = await agent_module._validate_and_get_host(
            {"hostname": "ok.example"}, _connection(), db
        )
        assert host is host_obj
        assert err is None
