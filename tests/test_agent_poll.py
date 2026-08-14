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

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api import agent_poll


@pytest.fixture(name="client")
def _client():
    from fastapi import FastAPI  # noqa: PLC0415

    app = FastAPI()
    app.include_router(agent_poll.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(name="valid_token")
def _valid_token():
    with patch.object(
        agent_poll.websocket_security, "validate_connection_token", return_value=True
    ):
        yield "Bearer good-token"


def test_missing_token_is_rejected(client):
    """Registration is unauthenticated by design; polling is NOT."""
    response = client.post("/api/agent/poll", json={"host_id": "h1"})
    assert response.status_code == 401


def test_invalid_token_is_rejected(client):
    with patch.object(
        agent_poll.websocket_security, "validate_connection_token", return_value=False
    ):
        response = client.post(
            "/api/agent/poll",
            json={"host_id": "h1"},
            headers={"Authorization": "Bearer nope"},
        )
    assert response.status_code == 401


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
                "host_id": "host-abc",
                "messages": [
                    {"message_type": "heartbeat", "data": {"up": True}},
                    {"message_type": "os_version_update", "data": {"v": "26.04"}},
                ],
            },
            headers={"Authorization": valid_token},
        )

    assert response.status_code == 200
    assert enqueue.call_count == 2
    kwargs = enqueue.call_args_list[0].kwargs
    assert kwargs["message_type"] == "heartbeat"
    assert kwargs["host_id"] == "host-abc"
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
            json={"host_id": "host-abc"},
            headers={"Authorization": valid_token},
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
                "host_id": "h",
                "messages": [
                    {"message_type": "bad", "data": {}},
                    {"message_type": "good", "data": {}},
                ],
            },
            headers={"Authorization": valid_token},
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
            json={"host_id": "h"},
            headers={"Authorization": valid_token},
        )
    assert response.json()["poll_interval"] == 1


def test_batch_size_is_bounded(client, valid_token):
    """An offline-for-a-week host must not produce a response a proxy truncates."""
    with patch.object(agent_poll.server_queue_manager, "enqueue_message"), patch.object(
        agent_poll.server_queue_manager, "dequeue_messages_for_host", return_value=[]
    ) as dequeue:
        client.post(
            "/api/agent/poll",
            json={"host_id": "h"},
            headers={"Authorization": valid_token},
        )
    assert dequeue.call_args.kwargs["limit"] == agent_poll.MAX_MESSAGES_PER_POLL
