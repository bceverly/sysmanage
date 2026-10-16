# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every outbound message type a server path enqueues is one the outbound
processor delivers.

host_approved and broadcast were enqueued but failed as "Unknown outbound
message type": no agent ever received its approval notice, so none reset its
send-on-change memory, and reports sent while the host was still pending
(and dropped by the server) were not re-sent for a day.  beast's hardware
and network interfaces were missing and network discovery called it
unmanaged (production, 2026-10-16)."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.websocket import outbound_processor as op

BACKEND = Path(__file__).resolve().parents[2] / "backend"
HANDLED_BY_COMMAND_BRANCH = {"command"}
TYPE_CONSTANTS = {
    "MessageType.BROADCAST.value": "broadcast",
    "MessageType.LOGGING_CONFIG_UPDATE.value": "logging_config_update",
    "MessageType.CONFIG_UPDATE.value": "config_update",
}
# Enqueued by a server path but deliberately undeliverable today: the agent
# has no handler for it.  Listed so adding a new type is still a decision.
KNOWN_UNDELIVERED = {"config_update"}


def _enqueued_outbound_types():
    found = set()
    for path in BACKEND.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for call in re.finditer(r"enqueue_message\((.*?)\)\n", text, re.S):
            block = call.group(1)
            if "OUTBOUND" not in block:
                continue
            typed = re.search(r"message_type=([^,\n]+)", block)
            if typed:
                raw = typed.group(1).strip()
                found.add(TYPE_CONSTANTS.get(raw, raw.strip("\"'")))
    return found


def test_every_enqueued_outbound_type_is_delivered():
    enqueued = _enqueued_outbound_types()
    assert "host_approved" in enqueued  # the scan itself still works
    handled = HANDLED_BY_COMMAND_BRANCH | set(op.NOTICE_MESSAGE_TYPES)
    unhandled = enqueued - handled - KNOWN_UNDELIVERED
    assert (
        not unhandled
    ), f"enqueued outbound types the processor fails as unknown: {sorted(unhandled)}"


@pytest.mark.asyncio
@pytest.mark.parametrize("message_type", ["host_approved", "broadcast"])
async def test_a_notice_is_sent_and_completed(message_type):
    message = SimpleNamespace(message_id="m1", message_type=message_type)
    host = SimpleNamespace(id="h1", fqdn="beast")
    with patch.object(op, "_awaiting_poll", return_value=False), patch.object(
        op.server_queue_manager, "mark_processing", return_value=True
    ), patch.object(
        op.server_queue_manager,
        "deserialize_message_data",
        return_value={"message_type": message_type, "data": {"host_id": "h1"}},
    ), patch.object(
        op, "send_message_to_agent", new=AsyncMock(return_value=True)
    ) as send, patch.object(
        op.server_queue_manager, "mark_completed"
    ) as completed, patch.object(
        op.server_queue_manager, "mark_failed"
    ) as failed:
        await op.process_outbound_message(message, host, db=None)
    send.assert_awaited_once()
    completed.assert_called_once_with("m1", db=None)
    failed.assert_not_called()


@pytest.mark.asyncio
async def test_an_undelivered_notice_is_failed_for_a_retry():
    message = SimpleNamespace(message_id="m2", message_type="host_approved")
    host = SimpleNamespace(id="h1", fqdn="beast")
    with patch.object(op, "_awaiting_poll", return_value=False), patch.object(
        op.server_queue_manager, "mark_processing", return_value=True
    ), patch.object(
        op.server_queue_manager, "deserialize_message_data", return_value={}
    ), patch.object(
        op, "send_message_to_agent", new=AsyncMock(return_value=False)
    ), patch.object(
        op.server_queue_manager, "mark_completed"
    ) as completed, patch.object(
        op.server_queue_manager, "mark_failed"
    ) as failed:
        await op.process_outbound_message(message, host, db=None)
    completed.assert_not_called()
    failed.assert_called_once()


@pytest.fixture(autouse=True)
def _host_has_a_live_connection(monkeypatch):
    """These tests exercise the send paths, which run only for a host this
    process holds a socket for; a disconnected host's commands are held
    without spending a retry (tests/websocket/test_late_acknowledgment.py)."""
    from backend.websocket import outbound_processor as _outbound  # noqa: PLC0415

    monkeypatch.setattr(_outbound, "_connected", lambda host: True)
