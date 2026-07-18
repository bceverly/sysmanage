# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""End-to-end maintenance-window gating (Phase 15 exit item).

Proves the *queue -> window -> execute* path: an outbound gated operation
(``command``) is enqueued for an approved host, then driven through the real
outbound processor with the real queue manager.  We assert that:

* with the host inside a **blackout** (or outside its allow-window) the message
  is **held** -- it stays ``PENDING`` and no websocket send happens; then when a
  window is **open** the same message **releases/executes** (``SENT``);
* with **no window configured** the message dispatches normally (fail-open);
* windows are **opt-in per host** -- a window scoped to another host does not
  freeze this host.

Only the leaf websocket send (``connection_manager.send_to_host``) is mocked;
everything from the pending-message query, the maintenance-window evaluation,
through the queue-manager status transitions runs for real.  "Now" is pinned to
a fixed instant so recurrence math is deterministic (no wall-clock flakiness).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.persistence.models import (
    Host,
    MaintenanceWindow,
    MaintenanceWindowScope,
    MessageQueue,
)
from backend.websocket import outbound_processor
from backend.websocket.outbound_processor import process_outbound_messages
from backend.websocket.queue_manager import QueueDirection, QueueStatus

# A fixed reference "now" (aware UTC): Saturday 2026-07-11 12:00.  The processor
# converts it to naive UTC internally; pinning it removes wall-clock flakiness
# from the zoneinfo recurrence evaluation.
NOW_AWARE = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
NOW = NOW_AWARE.replace(tzinfo=None)


class _FrozenDateTime(datetime):
    """datetime subclass whose now() returns our pinned instant."""

    @classmethod
    def now(cls, tz=None):  # noqa: D401 - mirror datetime.now signature
        if tz is not None:
            return NOW_AWARE.astimezone(tz)
        return NOW_AWARE.replace(tzinfo=None)


def _approved_host(session):
    host = Host(
        id=str(uuid4()),
        fqdn="gated-host.example.com",
        ipv4="192.168.50.10",
        active=True,
        platform="Ubuntu",
        platform_release="22.04",
        approval_status="approved",
    )
    session.add(host)
    session.commit()
    return host


def _enqueue_command(session, host_id):
    """Enqueue a gated outbound ``command`` for a host, return its message_id."""
    message = MessageQueue(
        message_id=str(uuid4()),
        host_id=host_id,
        direction=QueueDirection.OUTBOUND,
        status=QueueStatus.PENDING,
        priority="normal",
        message_type="command",
        message_data='{"data": {"command_type": "install_package"}}',
        created_at=NOW,
    )
    session.add(message)
    session.commit()
    return message.message_id


def _mk_window(session, host_id, *, kind="allow", start_time, duration_minutes):
    """Create an enabled daily window scoped to one host."""
    window = MaintenanceWindow(
        name=f"{kind}-window",
        kind=kind,
        recurrence="daily",
        timezone="UTC",
        start_time=start_time,
        duration_minutes=duration_minutes,
        enabled=True,
    )
    session.add(window)
    session.flush()
    session.add(
        MaintenanceWindowScope(window_id=window.id, scope_type="host", host_id=host_id)
    )
    session.commit()
    return window


def _status(session, message_id):
    msg = session.query(MessageQueue).filter_by(message_id=message_id).first()
    return None if msg is None else msg.status


async def _run(session):
    """Drive the outbound processor with a pinned clock and a mocked wire send.

    Returns the send_to_host mock so callers can assert whether a dispatch
    actually reached the (mocked) websocket layer.
    """
    send_mock = AsyncMock(return_value=True)
    with patch.object(outbound_processor, "datetime", _FrozenDateTime), patch(
        "backend.websocket.connection_manager.connection_manager.send_to_host",
        send_mock,
    ):
        await process_outbound_messages(session)
    return send_mock


@pytest.mark.asyncio
async def test_fail_open_no_window_dispatches(session):
    """No window configured -> message dispatches normally (fail-open default)."""
    host = _approved_host(session)
    message_id = _enqueue_command(session, host.id)

    send_mock = await _run(session)

    assert send_mock.called
    assert _status(session, message_id) == QueueStatus.SENT


@pytest.mark.asyncio
async def test_opt_in_other_host_window_does_not_gate(session):
    """A window scoped to a *different* host must not freeze this host."""
    host = _approved_host(session)
    # A closed allow-window, but scoped to some other host.
    _mk_window(
        session,
        str(uuid4()),
        start_time="02:00",
        duration_minutes=60,  # 02:00-03:00, closed at 12:00
    )
    message_id = _enqueue_command(session, host.id)

    send_mock = await _run(session)

    assert send_mock.called
    assert _status(session, message_id) == QueueStatus.SENT


@pytest.mark.asyncio
async def test_blackout_holds_then_release_executes(session):
    """queue -> blackout (held/PENDING) -> blackout cleared (released/SENT)."""
    host = _approved_host(session)
    message_id = _enqueue_command(session, host.id)

    # Blackout 11:30-12:30 contains 12:00 -> the message must be HELD.
    blackout = _mk_window(
        session,
        host.id,
        kind="blackout",
        start_time="11:30",
        duration_minutes=60,
    )

    send_mock = await _run(session)
    assert not send_mock.called, "gated message must not reach the wire during blackout"
    assert _status(session, message_id) == QueueStatus.PENDING, "held, not consumed"

    # Clear the blackout (operator disables it); same still-PENDING message now
    # releases and executes on the next tick.
    blackout.enabled = False
    session.commit()

    send_mock = await _run(session)
    assert send_mock.called
    assert _status(session, message_id) == QueueStatus.SENT


@pytest.mark.asyncio
async def test_closed_allow_window_holds_then_open_executes(session):
    """queue -> outside allow-window (held) -> window open (released/SENT)."""
    host = _approved_host(session)
    message_id = _enqueue_command(session, host.id)

    # Allow-window 02:00-03:00 does NOT contain 12:00 -> outside the window.
    window = _mk_window(
        session,
        host.id,
        start_time="02:00",
        duration_minutes=60,
    )

    send_mock = await _run(session)
    assert not send_mock.called, "outside the allow-window the message must be held"
    assert _status(session, message_id) == QueueStatus.PENDING

    # Widen the window so 12:00 falls inside it (10:00-14:00); the same message
    # is now released and executes.
    window.start_time = "10:00"
    window.duration_minutes = 240
    session.commit()

    send_mock = await _run(session)
    assert send_mock.called
    assert _status(session, message_id) == QueueStatus.SENT
