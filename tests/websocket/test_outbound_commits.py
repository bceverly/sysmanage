# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""No row lock across an await in the outbound pass (Phase 27 S5, 2026-11-18).

The pass shared one session and committed once per cycle, so a message's
claim (an UPDATE -- a row lock) stayed open across the send's ``await``.  The
agent's acknowledgement of that row, and another worker's claim of it, then
blocked their event loops on the lock: every loop stalled ~30 s in a load test
asking 2,000 hosts to update their agents at once."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.websocket import outbound_processor as op


@pytest.mark.asyncio
async def test_the_claim_is_committed_before_the_send_and_the_outcome_after():
    events = []
    db = MagicMock()
    db.commit.side_effect = lambda: events.append("commit")
    message = SimpleNamespace(message_id="m1", message_type="command")
    host = SimpleNamespace(id="h1", fqdn="h1.example")

    async def send(*_args, **_kwargs):
        events.append("send")
        return True

    with patch.object(op, "_awaiting_poll", return_value=False), patch.object(
        op, "_connected", return_value=True
    ), patch.object(
        op.server_queue_manager,
        "mark_processing",
        side_effect=lambda *a, **k: events.append("claim") or True,
    ), patch.object(
        op.server_queue_manager, "deserialize_message_data", return_value={}
    ), patch.object(
        op, "send_command_to_agent", new=send
    ), patch.object(
        op.server_queue_manager,
        "mark_sent",
        side_effect=lambda *a, **k: events.append("sent"),
    ), patch.object(
        op, "_log_command_sent"
    ):
        await op.process_outbound_message(message, host, db)

    assert events == ["claim", "commit", "send", "sent", "commit"]


@pytest.mark.asyncio
async def test_a_failed_send_still_commits_its_outcome():
    db = MagicMock()
    message = SimpleNamespace(message_id="m2", message_type="command")
    host = SimpleNamespace(id="h1", fqdn="h1.example")
    with patch.object(op, "_awaiting_poll", return_value=False), patch.object(
        op, "_connected", return_value=True
    ), patch.object(
        op.server_queue_manager, "mark_processing", return_value=True
    ), patch.object(
        op.server_queue_manager, "deserialize_message_data", return_value={}
    ), patch.object(
        op, "send_command_to_agent", new=AsyncMock(side_effect=RuntimeError("boom"))
    ), patch.object(
        op.server_queue_manager, "mark_failed"
    ) as failed:
        await op.process_outbound_message(message, host, db)
    failed.assert_called_once()
    db.rollback.assert_called_once()
    assert db.commit.call_count == 2  # the claim, then the failure
