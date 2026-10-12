# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Where the clock measurement touches the socket (Phase 23.3 S2): t1 on every
send, t4 on a heartbeat, and the refused-timestamp heartbeat."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api import agent as agent_module
from backend.services import clock_tracking
from backend.websocket.connection_manager import AgentConnection


def test_every_send_carries_t1_on_a_copy():
    websocket = MagicMock()
    websocket.send_text = AsyncMock()
    conn = AgentConnection(websocket)
    original = {"message_type": "command", "data": {}}
    before = time.time()
    assert asyncio.run(conn.send_message(original))
    sent = json.loads(websocket.send_text.call_args.args[0])
    assert before <= sent["clock"]["t1"] <= time.time()
    assert "clock" not in original  # callers may reuse their dict


def test_a_valid_heartbeat_is_measured():
    conn = SimpleNamespace(host_id="h")
    clock = {"t1": 100.0, "t2": 100.51, "t3": 101.01, "hold": 0.5}
    agent_module._observe_clock(
        {"message_type": "heartbeat", "clock": clock}, conn, None, 100.52, True, None
    )
    assert clock_tracking.current(conn)["offset_ms"] == 500.0


def test_only_heartbeats_with_a_receive_time_are_measured():
    conn = SimpleNamespace()
    clock = {"t1": 100.0, "t2": 100.51, "t3": 101.01, "hold": 0.5}
    agent_module._observe_clock(
        {"message_type": "system_info", "clock": clock}, conn, None, 100.52, True, None
    )
    agent_module._observe_clock(
        {"message_type": "heartbeat", "clock": clock}, conn, None, None, True, None
    )
    agent_module._observe_clock("junk", conn, None, 100.52, True, None)
    assert clock_tracking.current(conn) is None


def test_a_heartbeat_refused_for_its_timestamp_is_still_reported():
    conn = SimpleNamespace(host_id="h")
    db = MagicMock()
    now = time.time()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now + 3600))
    with patch(
        "backend.persistence.partitions.tenant_engine_for_host", return_value=None
    ), patch.object(clock_tracking, "persist_if_due") as persist:
        agent_module._observe_clock(
            {"message_type": "heartbeat", "timestamp": stamp},
            conn,
            db,
            now,
            False,
            "Message timestamp too old (3600s) in heartbeat message",
        )
    figure = clock_tracking.current(conn)
    assert figure["method"] == "timestamp"
    assert abs(figure["offset_ms"] - 3_600_000) < 1500
    persist.assert_called_once_with(conn, db.get_bind.return_value)


def test_other_refusals_and_unbound_connections_are_not_measured():
    for conn, error in (
        (SimpleNamespace(host_id="h"), "Missing required field"),
        (SimpleNamespace(), "Message timestamp too old (3600s)"),
    ):
        agent_module._observe_clock(
            {"message_type": "heartbeat", "timestamp": "2026-10-12T12:00:00"},
            conn,
            MagicMock(),
            time.time(),
            False,
            error,
        )
        assert clock_tracking.current(conn) is None


def test_a_resync_result_is_routed_to_its_row():
    from backend.api import message_handlers  # noqa: PLC0415

    with patch("backend.services.clock_resync.record_result") as record:
        out = asyncio.run(
            message_handlers.handle_command_result(
                MagicMock(),
                SimpleNamespace(hostname="x13s"),
                {"command_id": "c1", "command_type": "resync_clock", "success": True},
            )
        )
    assert out is None
    record.assert_called_once()
