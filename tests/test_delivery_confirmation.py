# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Delivery confirmation (2026-11-06): an agent forgets a message only once
the server has stored it.  Before, a message sent while PostgreSQL was down
(a restart, an upgrade, a backup's pause) was lost from both ends."""

# pylint: disable=protected-access

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.api import agent as agent_api
from backend.api import agent_poll
from backend.persistence.models import MessageQueue
from backend.websocket import delivery_confirmation as delivery


class _Connection(SimpleNamespace):
    def __init__(self, confirms=True, host_id=None):
        super().__init__(
            agent_id="c-1", hostname="web.example.com", host_id=host_id,
            ipv4=None, ipv6=None, platform=None, sent=[],
        )  # fmt: skip
        if confirms:
            self.delivery_confirmation = True

    async def send_message(self, message):
        self.sent.append(message)


def _raw(message_type="hardware_update", message_id="m-1", **data):
    return json.dumps({"message_type": message_type, "message_id": message_id,
                       "timestamp": "2026-11-06T12:00:00Z", "data": data})  # fmt: skip


def _confirmed(connection):
    return [
        m["data"] for m in connection.sent if m["message_type"] == delivery.MESSAGE_TYPE
    ]


@pytest.fixture
def valid():
    with patch.object(agent_api.websocket_security, "validate_message_integrity",
                      return_value=(True, None)):  # fmt: skip
        yield


@pytest.mark.asyncio
async def test_a_stored_message_is_confirmed(valid):
    connection = _Connection()
    with patch.object(
        agent_api, "_enqueue_inbound_message", return_value=delivery.STORED
    ):
        await agent_api._process_websocket_message(_raw(), connection, None, "c-1")
    assert _confirmed(connection) == [{"message_id": "m-1", "status": "stored"}]


@pytest.mark.asyncio
async def test_nothing_is_confirmed_while_the_database_is_down(valid):
    """The agent keeps the message and sends it again."""
    connection = _Connection()
    with patch.object(agent_api, "_enqueue_inbound_message",
                      side_effect=RuntimeError("could not connect to server")):  # fmt: skip
        await agent_api._process_websocket_message(_raw(), connection, None, "c-1")
    assert _confirmed(connection) == []
    assert connection.sent[-1]["error_type"] == "processing_error"


@pytest.mark.asyncio
async def test_a_buffered_message_waits_for_its_resend(valid):
    connection = _Connection()
    with patch.object(
        agent_api, "_enqueue_inbound_message", return_value=delivery.BUFFERED
    ):
        await agent_api._process_websocket_message(_raw(), connection, None, "c-1")
    assert _confirmed(connection) == []


@pytest.mark.asyncio
async def test_a_message_that_fails_validation_is_rejected_not_retried():
    connection = _Connection()
    with patch.object(agent_api.websocket_security, "validate_message_integrity",
                      return_value=(False, "bad timestamp")):  # fmt: skip
        await agent_api._process_websocket_message(_raw(), connection, None, "c-1")
    assert _confirmed(connection) == [{"message_id": "m-1", "status": "rejected"}]


@pytest.mark.asyncio
async def test_an_older_agent_is_sent_no_confirmations(valid):
    connection = _Connection(confirms=False)
    with patch.object(
        agent_api, "_enqueue_inbound_message", return_value=delivery.STORED
    ):
        await agent_api._process_websocket_message(_raw(), connection, None, "c-1")
    assert _confirmed(connection) == []


@pytest.mark.asyncio
async def test_system_info_says_whether_the_agent_waits(valid):
    connection = _Connection(confirms=False)
    with patch.object(agent_api, "_handle_time_sensitive_message"):
        await agent_api._process_websocket_message(
            _raw("system_info", "s-1", delivery_confirmation=1), connection, None, "c-1"
        )
    assert connection.delivery_confirmation is True
    assert _confirmed(connection) == [{"message_id": "s-1", "status": "stored"}]


def test_a_resent_message_is_stored_once(session):
    connection = _Connection()
    message = SimpleNamespace(message_type="hardware_update", message_id="m-7", data={})
    assert agent_api._enqueue_inbound_message(message, connection, session) == "stored"
    assert agent_api._enqueue_inbound_message(message, connection, session) == "stored"
    assert session.query(MessageQueue).filter_by(message_id="m-7").count() == 1


def test_a_message_claiming_another_host_is_rejected():
    connection = _Connection(host_id="h-1")
    message = SimpleNamespace(message_type="hardware_update", message_id="m-8",
                              data={"host_id": "h-2"})  # fmt: skip
    assert agent_api._enqueue_inbound_message(message, connection, None) == "rejected"


def test_a_polled_resend_is_stored_once(session):
    payload = agent_poll.PollRequest(host_id="h", messages=[
        agent_poll.PolledMessage(message_type="hardware_update", message_id="p-1")])  # fmt: skip
    with patch.object(agent_poll.server_queue_manager, "enqueue_message") as enqueue, \
            patch.object(agent_poll.server_queue_manager, "dequeue_messages_for_host",
                         return_value=[]):  # fmt: skip
        session.add(MessageQueue(message_id="p-1", direction="inbound",
                                 message_type="hardware_update", message_data="{}",
                                 status="pending", priority="normal",
                                 created_at=datetime(2026, 11, 6)))  # fmt: skip
        session.flush()
        agent_poll._exchange(session, "h", payload)
    enqueue.assert_not_called()
