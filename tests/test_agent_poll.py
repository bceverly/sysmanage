# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The HTTP fallback must be a transport swap, not a second messaging system.

Some proxies refuse to tunnel a WebSocket Upgrade. Measured against a real HTTP
CONNECT proxy returning 403, the agent gets ``InvalidProxyStatus: proxy rejected
connection: HTTP 403`` and has NO connection -- so every command and every
inventory update is undeliverable and the host is simply invisible.

This endpoint drains the SAME queue the WebSocket drains. These tests pin that:
a polled message must be indistinguishable, downstream, from a socketed one.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import agent_poll
from backend.persistence import models
from backend.persistence.db import Base, get_db
from backend.websocket import outbound_processor, poll_presence

HOST = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
SECRET = "host-secret-of-HOST"


def _sessionmaker():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    for host_id, fqdn, secret in (
        (HOST, "a.example", SECRET),
        (OTHER, "b.example", "b"),
    ):
        session.add(
            models.Host(
                id=uuid.UUID(host_id), fqdn=fqdn, active=True, status="up",
                approval_status="approved", host_token=secret,
            )
        )  # fmt: skip
    session.commit()
    session.close()
    return make


@pytest.fixture(name="bootstrap")
def _bootstrap():
    make = _sessionmaker()
    yield make
    make.kw["bind"].dispose()


@pytest.fixture(name="client")
def _client(bootstrap):
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(agent_poll.router, prefix="/api")

    def _db():
        session = bootstrap()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    with patch.object(agent_poll, "tenant_engine_for_host", return_value=None):
        yield TestClient(app)
    poll_presence.forget(HOST)


@pytest.fixture(name="valid_token")
def _valid_token():
    # The REAL shape: (is_valid, connection_id, error).  The old fixture
    # returned a bare True, which is how a check that tested the (always
    # truthy) tuple itself passed its tests while accepting any token.
    with patch.object(
        agent_poll.websocket_security,
        "validate_connection_token",
        return_value=(True, "conn-1", ""),
    ):
        yield "Bearer good-token"


def _auth(token):
    return {"Authorization": token, "X-Host-Token": SECRET}


def test_missing_token_is_rejected(client):
    """Registration is unauthenticated by design; polling is NOT."""
    response = client.post("/api/agent/poll", json={"host_id": HOST})
    assert response.status_code == 401


def test_invalid_token_is_rejected(client):
    """REGRESSION: the validator returns a tuple; an invalid token must 401."""
    with patch.object(
        agent_poll.websocket_security,
        "validate_connection_token",
        return_value=(False, None, "Invalid token signature"),
    ):
        response = client.post(
            "/api/agent/poll",
            json={"host_id": HOST},
            headers=_auth("Bearer nope"),
        )
    assert response.status_code == 401


def test_a_valid_token_without_the_hosts_own_secret_is_rejected(client, valid_token):
    """A connection token proves only "some agent"; polling as a host needs
    that host's secret, or one agent could drain another host's queue."""
    for headers in (
        {"Authorization": valid_token},
        {"Authorization": valid_token, "X-Host-Token": "b"},  # OTHER's secret
        {"Authorization": valid_token, "X-Host-Token": "guess"},
    ):
        response = client.post(
            "/api/agent/poll", json={"host_id": HOST}, headers=headers
        )
        assert response.status_code == 401, headers


def test_an_unknown_or_malformed_host_is_rejected(client, valid_token):
    for host_id in (str(uuid.uuid4()), "not-a-uuid"):
        response = client.post(
            "/api/agent/poll", json={"host_id": host_id}, headers=_auth(valid_token)
        )
        assert response.status_code == 401, host_id


def test_a_tenant_host_is_served_from_its_tenant_database(bootstrap, valid_token):
    """The host's row and queue live in its TENANT database.  Served from the
    bootstrap one, its inbound messages were dropped and its queue unread."""
    from fastapi import FastAPI  # noqa: PLC0415

    tenant = _sessionmaker()
    app = FastAPI()
    app.include_router(agent_poll.router, prefix="/api")
    empty_engine = create_engine("sqlite://")
    empty = sessionmaker(bind=empty_engine)  # the host is NOT in this database

    def _db():
        session = empty()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    with patch.object(
        agent_poll, "tenant_engine_for_host", return_value=tenant.kw["bind"]
    ), patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=[]
    ) as dequeue:
        response = TestClient(app).post(
            "/api/agent/poll", json={"host_id": HOST}, headers=_auth(valid_token)
        )
    assert response.status_code == 200
    assert dequeue.call_args.kwargs["db"].get_bind() is tenant.kw["bind"]
    poll_presence.forget(HOST)
    tenant.kw["bind"].dispose()
    empty_engine.dispose()


def test_a_successful_poll_marks_the_host_as_polling(client, valid_token):
    poll_presence.forget(HOST)
    client.post("/api/agent/poll", json={"host_id": HOST}, headers=_auth(valid_token))
    assert poll_presence.recently_polled(HOST)


def test_commands_for_a_polling_host_are_left_for_the_poll():
    """The outbound processor used to try the (absent) socket and FAIL every
    command within seconds, before the poll could collect it."""

    class _Host:
        id, fqdn = HOST, "a.example"

    poll_presence.touch(HOST)
    try:
        with patch.object(
            outbound_processor.server_queue_manager, "mark_processing"
        ) as processing, patch(
            "backend.websocket.connection_manager.connection_manager.get_agent_by_hostname",
            return_value=None,
        ):
            import asyncio  # noqa: PLC0415

            asyncio.run(
                outbound_processor.process_outbound_message(object(), _Host(), None)
            )
        processing.assert_not_called()
    finally:
        poll_presence.forget(HOST)


def test_presence_expires():
    poll_presence.touch(HOST)
    later = __import__("time").monotonic() + poll_presence.POLL_PRESENCE_SECONDS + 1
    assert not poll_presence.recently_polled(HOST, now=later)
    poll_presence.forget(HOST)


def test_inbound_messages_are_enqueued_like_the_websocket_does(client, valid_token):
    """A polled message must reach the SAME inbound queue.

    If it went anywhere else, the inbound processor would not see it and the
    two transports would quietly behave differently.
    """
    with patch.object(
        agent_poll.server_queue_manager, "enqueue_message"
    ) as enqueue, patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=[]
    ):
        response = client.post(
            "/api/agent/poll",
            json={
                "host_id": HOST,
                "messages": [
                    {"message_type": "heartbeat", "data": {"up": True}},
                    {"message_type": "os_version_update", "data": {"v": "26.04"}},
                ],
            },
            headers=_auth(valid_token),
        )

    assert response.status_code == 200
    assert enqueue.call_count == 2
    kwargs = enqueue.call_args_list[0].kwargs
    assert kwargs["message_type"] == "heartbeat"
    assert kwargs["host_id"] == HOST
    assert kwargs["direction"] == agent_poll.QueueDirection.INBOUND


def test_pending_commands_come_back_and_are_marked_sent(client, valid_token):
    """Returning a command without marking it sent would deliver it forever."""

    class _Queued:
        def __init__(self, mid, mtype, data):
            self.message_id, self.message_type, self.message_data = mid, mtype, data

    queued = [
        _Queued("m1", "command", {"command_type": "collect_packages"}),
        _Queued("m2", "command", {"command_type": "reboot"}),
    ]
    with patch.object(agent_poll.server_queue_manager, "enqueue_message"), patch.object(
        agent_poll.server_queue_manager,
        "dequeue_messages_for_host",
        return_value=queued,
    ), patch.object(agent_poll.server_queue_manager, "mark_sent") as mark:
        response = client.post(
            "/api/agent/poll",
            json={"host_id": HOST},
            headers=_auth(valid_token),
        )

    body = response.json()
    assert [m["message_id"] for m in body["messages"]] == ["m1", "m2"]
    assert body["messages"][0]["data"]["command_type"] == "collect_packages"
    assert [c.args[0] for c in mark.call_args_list] == ["m1", "m2"]


def test_one_bad_message_does_not_lose_the_others(client, valid_token):
    """A single unenqueueable message must not discard the whole poll."""
    with patch.object(
        agent_poll.server_queue_manager,
        "enqueue_message",
        side_effect=[RuntimeError("boom"), None],
    ), patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=[]
    ):
        response = client.post(
            "/api/agent/poll",
            json={
                "host_id": HOST,
                "messages": [
                    {"message_type": "bad", "data": {}},
                    {"message_type": "good", "data": {}},
                ],
            },
            headers=_auth(valid_token),
        )
    assert response.status_code == 200


def test_a_full_batch_asks_the_agent_back_sooner(client, valid_token):
    """A backlog should drain, not trickle out one interval at a time."""

    class _Q:
        def __init__(self, i):
            self.message_id, self.message_type, self.message_data = (
                f"m{i}",
                "command",
                {},
            )

    full = [_Q(i) for i in range(agent_poll.MAX_MESSAGES_PER_POLL)]
    with patch.object(agent_poll.server_queue_manager, "enqueue_message"), patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=full
    ), patch.object(agent_poll.server_queue_manager, "mark_sent"):
        response = client.post(
            "/api/agent/poll",
            json={"host_id": HOST},
            headers=_auth(valid_token),
        )
    assert response.json()["poll_interval"] == 1


def test_batch_size_is_bounded(client, valid_token):
    """An offline-for-a-week host must not produce a response a proxy truncates."""
    with patch.object(agent_poll.server_queue_manager, "enqueue_message"), patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=[]
    ) as dequeue:
        client.post(
            "/api/agent/poll",
            json={"host_id": HOST},
            headers=_auth(valid_token),
        )
    assert dequeue.call_args.kwargs["limit"] == agent_poll.MAX_MESSAGES_PER_POLL
