# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.0 -- a host is its credential, not its name.

Pins the identity rules (backend/security/agent_identity.py) and the places
that enforce them: the SYSTEM_INFO handshake, command acknowledgments and the
inbound enqueue.  The end-to-end proof against a running server is the
harness's ``agent-impersonation`` scenario (tests/load/security_scenarios.py).
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import agent as agent_api
from backend.api import message_handlers, message_handlers_core
from backend.persistence import models
from backend.persistence.db import Base
from backend.security import agent_identity as ident

TOKEN = "t" * 40


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    with sessionmaker(bind=eng)() as session:
        yield session
    eng.dispose()


def _host(db, fqdn="web.example.com", token=TOKEN, **extra):
    host = models.Host(
        fqdn=fqdn, active=True, approval_status="approved", host_token=token, **extra
    )
    db.add(host)
    db.commit()
    return host


def _claim(db, **data):
    return ident.check_claim(db, data)


# -- the rules ----------------------------------------------------------------


def test_an_unknown_host_is_new(db):
    assert _claim(db, hostname="fresh.example.com").verdict == ident.NEW


def test_a_host_that_never_had_a_token_is_first_use(db):
    _host(db, token=None)
    assert _claim(db, hostname="web.example.com").verdict == ident.FIRST_USE


def test_the_right_token_is_verified(db):
    host = _host(db)
    claim = _claim(db, hostname=host.fqdn, host_id=str(host.id), host_token=TOKEN)
    assert claim.verdict == ident.VERIFIED


def test_a_wrong_token_is_refused(db):
    host = _host(db)
    claim = _claim(db, hostname=host.fqdn, host_id=str(host.id), host_token="nope")
    assert (claim.verdict, claim.reason) == (ident.REFUSED, ident.CREDENTIAL_INVALID)


def test_a_bare_name_is_refused(db):
    """The defect: naming an approved host used to be enough."""
    _host(db)
    claim = _claim(db, hostname="web.example.com")
    assert (claim.verdict, claim.reason) == (ident.REFUSED, ident.CREDENTIAL_REQUIRED)


def test_id_without_token_is_legacy_until_the_host_is_ratcheted(db):
    host = _host(db)
    data = {"hostname": host.fqdn, "host_id": str(host.id)}
    assert ident.check_claim(db, data).verdict == ident.LEGACY
    host.requires_host_token = True
    db.commit()
    assert ident.check_claim(db, data).verdict == ident.REFUSED


def test_another_hosts_id_does_not_vouch_for_this_name(db):
    other = _host(db, fqdn="other.example.com", token="o" * 40)
    _host(db)
    claim = _claim(db, hostname="web.example.com", host_id=str(other.id))
    assert claim.verdict == ident.REFUSED


def test_the_ratchet_needs_the_capability_and_a_verified_token(db):
    host = _host(db)
    verified = ident.Claim(ident.VERIFIED, host)
    assert not ident.apply_ratchet(
        verified, {"agent_capabilities": {"capabilities": []}}
    )
    report = {
        "agent_capabilities": {"capabilities": [ident.PERSISTENT_TOKEN_CAPABILITY]}
    }
    assert not ident.apply_ratchet(ident.Claim(ident.LEGACY, host), report)
    assert ident.apply_ratchet(verified, report)
    assert host.requires_host_token is True


# -- the handshake ------------------------------------------------------------


def _connection():
    return SimpleNamespace(
        hostname=None,
        host_id=None,
        agent_id="conn-1",
        websocket=SimpleNamespace(client=SimpleNamespace(host="203.0.113.9")),
        send_message=AsyncMock(),
        is_mock_connection=True,
    )


@pytest.mark.asyncio
async def test_a_refused_handshake_binds_nothing_and_returns_no_token(db):
    _host(db)
    connection = _connection()
    reply = await message_handlers_core._handle_system_info_impl(
        db, connection, {"hostname": "web.example.com"}
    )
    assert reply["error_type"] == ident.CREDENTIAL_REQUIRED
    assert "host_token" not in reply
    assert connection.hostname is None and connection.host_id is None


@pytest.mark.asyncio
async def test_a_verified_handshake_binds_the_session(db):
    host = _host(db)
    connection = _connection()
    with patch("backend.api.agent.flush_pending_inbound_messages"), patch(
        "backend.websocket.connection_manager.connection_manager.register_agent"
    ) as register:
        reply = await message_handlers_core._handle_system_info_impl(
            db,
            connection,
            {"hostname": host.fqdn, "host_id": str(host.id), "host_token": TOKEN},
        )
    assert reply["message_type"] == "registration_success"
    assert connection.host_id == host.id
    register.assert_called_once()


# -- after the handshake ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_session_cannot_acknowledge_another_hosts_command(db):
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    db.add(
        models.MessageQueue(
            message_id="m-1", direction="outbound", message_type="command",
            message_data="{}", status="sent", priority="normal", host_id=theirs,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )  # fmt: skip
    db.commit()
    connection = SimpleNamespace(host_id=mine, hostname="web.example.com")
    with patch(
        "backend.websocket.queue_manager.server_queue_manager.mark_acknowledged"
    ) as ack:
        reply = await message_handlers.handle_command_acknowledgment(
            db, connection, {"message_id": "m-1"}
        )
    assert reply["error_type"] == "not_your_message"
    ack.assert_not_called()


def test_a_session_cannot_queue_data_for_another_host():
    connection = SimpleNamespace(
        hostname="web.example.com", host_id=uuid.uuid4(), agent_id="c",
        ipv4=None, ipv6=None, platform=None,
    )  # fmt: skip
    message = SimpleNamespace(
        message_type="os_version_update", message_id="x",
        data={"host_id": str(uuid.uuid4())},
    )  # fmt: skip
    with patch(
        "backend.websocket.queue_operations.QueueOperations.enqueue_message"
    ) as enqueue:
        agent_api._enqueue_inbound_message(message, connection, MagicMock())
    enqueue.assert_not_called()


def test_an_unproven_session_cannot_grow_its_buffer_without_limit():
    connection = SimpleNamespace(hostname=None, agent_id="c")
    message = SimpleNamespace(message_type="os_version_update", message_id="x", data={})
    for _ in range(agent_api.MAX_PENDING_INBOUND + 50):
        agent_api._enqueue_inbound_message(message, connection, MagicMock())
    assert len(connection._pending_inbound_messages) == agent_api.MAX_PENDING_INBOUND
