# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: the agent connection limit is keyed on identity, not IP.

It was 20 attempts per IP per 15 minutes for everyone: behind a NAT or proxy
the 21st agent was locked out (the scale harness: 196 refusals from 100
agents behind one address), every refused agent was told to come back in
exactly 900 s, and the tracking table never shrank.  ``X-Forwarded-For`` was
taken from anyone, left-most first.
"""

import ipaddress
import time
from unittest.mock import patch
from uuid import uuid4

from backend.persistence.models import Host
from backend.security import client_address as ca
from backend.security.agent_identity import verified_host_id
from backend.security.communication_security import WebSocketSecurityManager

LOOPBACK = [ipaddress.ip_network("127.0.0.1/32"), ipaddress.ip_network("::1/128")]


# -- the client address ----------------------------------------------------------


def test_a_direct_client_is_its_own_address_whatever_it_claims():
    assert ca.client_address("203.0.113.9", "10.1.1.1", LOOPBACK) == "203.0.113.9"


def test_behind_the_proxy_the_appended_hop_is_the_client():
    # The client sent "6.6.6.6" itself; nginx appended the real 203.0.113.9.
    assert (
        ca.client_address("127.0.0.1", "6.6.6.6, 203.0.113.9", LOOPBACK)
        == "203.0.113.9"
    )


def test_a_chain_of_trusted_proxies_is_walked_from_the_right():
    proxies = LOOPBACK + [ipaddress.ip_network("10.0.0.0/8")]
    forwarded = "6.6.6.6, 203.0.113.9, 10.0.0.5"
    assert ca.client_address("127.0.0.1", forwarded, proxies) == "203.0.113.9"


def test_garbage_in_the_header_falls_back_to_the_peer():
    assert ca.client_address("127.0.0.1", "not-an-ip", LOOPBACK) == "127.0.0.1"


def test_trusted_proxies_come_from_config_and_default_to_loopback():
    assert ca.trusted_proxies({}) == LOOPBACK
    nets = ca.trusted_proxies({"security": {"trusted_proxies": ["10.0.0.0/8", "bad"]}})
    assert nets == [ipaddress.ip_network("10.0.0.0/8")]


# -- the limiter -----------------------------------------------------------------


def _manager(**limits):
    config = {"security": {"agent_connection_limits": limits}}
    with patch(
        "backend.security.communication_security.get_config", return_value=config
    ):
        return WebSocketSecurityManager()


def test_limits_come_from_config_with_safe_defaults():
    assert _manager().connection_limits() == {"per_host": 30, "per_address": 600,
                                              "window_seconds": 900}  # fmt: skip
    manager = _manager(per_host=5, per_address="lots")
    assert manager.connection_limits()["per_host"] == 5
    assert manager.connection_limits()["per_address"] == 600


def test_hosts_behind_one_address_do_not_share_an_allowance():
    manager = _manager(per_host=3)
    for index in range(100):  # a whole office behind one NAT address
        key = f"host:{index}"
        assert not manager.is_connection_rate_limited(key, 3)
        manager.record_connection_attempt(key)
    for _ in range(2):
        manager.record_connection_attempt("host:7")
    assert manager.is_connection_rate_limited("host:7", 3)
    assert not manager.is_connection_rate_limited("host:8", 3)


def test_old_attempts_leave_the_table():
    manager = _manager()
    manager.connection_attempts["ip:203.0.113.9"] = [time.time() - 5000]
    assert not manager.is_connection_rate_limited("ip:203.0.113.9", 1)
    assert "ip:203.0.113.9" not in manager.connection_attempts


def test_retry_after_is_jittered_and_bounded_by_the_window():
    manager = _manager(window_seconds=900)
    manager.connection_attempts["ip:x"] = [time.time() - 600]  # 300 s left
    waits = {manager.retry_after("ip:x") for _ in range(30)}
    assert all(299 <= wait <= 300 + 60 for wait in waits)
    assert len(waits) > 1  # not everyone told the same second


# -- /agent/auth -----------------------------------------------------------------


def test_a_verified_agent_is_limited_by_host(client):
    with (
        patch("backend.api.agent.verified_host_id", return_value="h-1"),
        patch("backend.api.agent.websocket_security") as security,
    ):
        security.connection_limits.return_value = {"per_host": 30, "per_address": 600}
        security.is_connection_rate_limited.return_value = False
        security.generate_connection_token.return_value = "t"
        client.post(
            "/api/agent/auth", headers={"x-host-id": "h-1", "x-host-token": "x"}
        )
    security.is_connection_rate_limited.assert_called_once_with("host:h-1", 30)
    security.record_connection_attempt.assert_called_once_with("host:h-1")


def test_an_agent_without_identity_is_limited_by_address(client):
    with (
        patch("backend.api.agent.verified_host_id", return_value=None),
        patch("backend.api.agent.websocket_security") as security,
    ):
        security.connection_limits.return_value = {"per_host": 30, "per_address": 600}
        security.is_connection_rate_limited.return_value = True
        security.retry_after.return_value = 123
        response = client.post("/api/agent/auth", headers={"x-host-token": "forged"})
    security.is_connection_rate_limited.assert_called_once_with("ip:testclient", 600)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "123"


# -- host verification -----------------------------------------------------------


def _host(session, token):
    host = Host(id=uuid4(), fqdn=f"{uuid4().hex[:8]}.example.com", active=True,
                approval_status="approved", host_token=token)  # fmt: skip
    session.add(host)
    session.commit()
    return host


def test_only_the_hosts_own_token_verifies(session):
    host = _host(session, "the-real-token")
    with patch(
        "backend.persistence.partitions.tenant_engine_for_host", return_value=None
    ):
        assert verified_host_id(str(host.id), "the-real-token") == str(host.id)
        assert verified_host_id(str(host.id), "a-guess") is None
        assert verified_host_id("not-a-uuid", "the-real-token") is None
        assert verified_host_id(str(host.id), None) is None
        assert verified_host_id(str(uuid4()), "the-real-token") is None
