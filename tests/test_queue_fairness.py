# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: retry scheduling and outbound starvation.

The outbound pass took the global top 20 pending messages: messages held by a
closed maintenance window or waiting for a polling agent sat at the head of
that list and starved every other host.  The no-ack sweep loaded every stale
row at once and, with several workers, could retry one message twice.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.persistence.models import Host, MessageQueue
from backend.services.maintenance_window_service import GATED_MESSAGE_TYPES
from backend.websocket import outbound_processor, poll_presence
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)
from backend.websocket.queue_operations import QueueOperations

GATED = sorted(GATED_MESSAGE_TYPES)[0]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host(session):
    host = Host(id=str(uuid4()), fqdn=f"{uuid4().hex[:8]}.example.com", active=True,
                approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _outbound(session, host, message_type="logging_config_update", age=0, **extra):
    message = MessageQueue(
        message_id=str(uuid4()), host_id=host.id, direction=QueueDirection.OUTBOUND,
        status=QueueStatus.PENDING, priority="normal", message_type=message_type,
        message_data="{}", created_at=_now() - timedelta(seconds=age), **extra,
    )  # fmt: skip
    session.add(message)
    session.commit()
    return message.message_id


def _row(session, message_id):
    session.flush()
    session.expire_all()
    return session.query(MessageQueue).filter_by(message_id=message_id).one()


async def _deliver(message, _host, db):
    """Stand-in for a successful WebSocket send."""
    server_queue_manager.mark_completed(message.message_id, db=db)


async def _drain(session, allowed=lambda _db, _host_id, _now: True):
    sent = AsyncMock(side_effect=_deliver)
    with (
        patch.object(outbound_processor, "process_outbound_message", sent),
        patch("backend.services.maintenance_window_service.is_dispatch_allowed",
              side_effect=allowed),
    ):  # fmt: skip
        more = await outbound_processor.process_outbound_messages(session)
    return more, [call.args[1].id for call in sent.call_args_list]


# -- outbound starvation -------------------------------------------------------


async def test_a_blocked_host_no_longer_starves_the_rest(session):
    blocked, other = _host(session), _host(session)
    held = [_outbound(session, blocked, GATED, age=600) for _ in range(25)]
    _outbound(session, other)  # newest of all: under the old top-20, never reached
    _more, sent_to = await _drain(
        session, allowed=lambda _db, host_id, _now: host_id != blocked.id
    )
    assert other.id in sent_to and blocked.id not in sent_to
    deferred = _row(session, held[0])
    assert deferred.status == QueueStatus.PENDING
    assert deferred.scheduled_at > _now()  # a stored not-before time


async def test_a_deferred_message_goes_out_once_its_time_comes(session):
    host = _host(session)
    message_id = _outbound(session, host, GATED,
                           scheduled_at=_now() - timedelta(seconds=1))  # fmt: skip
    _more, sent_to = await _drain(session)
    assert sent_to == [host.id]
    assert _row(session, message_id).status == QueueStatus.COMPLETED


async def test_ungated_pushes_still_go_to_a_blocked_host(session):
    host = _host(session)
    _outbound(session, host, GATED)
    _outbound(session, host, "logging_config_update")
    _more, sent_to = await _drain(session, allowed=lambda *_: False)
    assert sent_to == [host.id]  # the config push, not the gated command


async def test_polling_hosts_are_left_to_their_polls(session):
    polling, connected = _host(session), _host(session)
    _outbound(session, polling, age=600)
    _outbound(session, connected)
    poll_presence.touch(polling.id)
    try:
        _more, sent_to = await _drain(session)
    finally:
        poll_presence.forget(polling.id)
    assert sent_to == [connected.id]


async def test_every_host_is_served_in_one_drain(session):
    hosts = [_host(session) for _ in range(outbound_processor.OUTBOUND_HOST_BATCH + 10)]
    for host in hosts:
        _outbound(session, host)
    more, sent_to = await _drain(session)
    assert sorted(sent_to) == sorted(host.id for host in hosts)
    assert more is False


async def test_a_host_whose_message_stays_pending_does_not_hold_the_slots(session):
    """Even if the first batch's messages are not delivered, every other
    host is reached in the same drain."""
    hosts = [_host(session) for _ in range(outbound_processor.OUTBOUND_HOST_BATCH + 5)]
    for index, host in enumerate(hosts):
        _outbound(session, host, age=1000 - index)
    stuck = AsyncMock()  # never delivers: messages stay PENDING
    with patch.object(outbound_processor, "process_outbound_message", stuck):
        await outbound_processor.process_outbound_messages(session)
    reached = {call.args[1].id for call in stuck.call_args_list}
    assert reached == {host.id for host in hosts}


async def test_oldest_waiting_host_goes_first(session):
    old, new = _host(session), _host(session)
    _outbound(session, new, age=1)
    _outbound(session, old, age=900)
    _more, sent_to = await _drain(session)
    assert sent_to[0] == old.id


async def test_an_unapproved_hosts_messages_fail_instead_of_waiting(session):
    host = _host(session)
    host.approval_status = "pending"
    session.commit()
    message_id = _outbound(session, host)
    _more, sent_to = await _drain(session)
    assert not sent_to
    row = _row(session, message_id)
    assert row.retry_count == 1 and row.scheduled_at is not None  # backoff, not a spin


def test_poll_presence_lists_only_recent_pollers():
    poll_presence.touch("recent")
    try:
        assert "recent" in poll_presence.polling_host_ids()
        stale = poll_presence.POLL_PRESENCE_SECONDS + 1
        later = poll_presence.time.monotonic() + stale
        assert "recent" not in poll_presence.polling_host_ids(now=later)
    finally:
        poll_presence.forget("recent")


# -- the no-ack sweep ----------------------------------------------------------


def _sent(session, host, minutes_ago=5):
    message_id = _outbound(session, host, "command")
    row = _row(session, message_id)
    row.status = QueueStatus.SENT
    row.started_at = _now() - timedelta(minutes=minutes_ago)
    session.commit()
    return message_id


def test_the_sweep_is_bounded_and_oldest_first(session):
    host = _host(session)
    oldest = _sent(session, host, minutes_ago=30)
    _sent(session, host, minutes_ago=20)
    _sent(session, host, minutes_ago=10)
    with patch.object(QueueOperations, "NO_ACK_SWEEP_LIMIT", 2):
        assert server_queue_manager.retry_unacknowledged_messages(db=session) == 2
        assert _row(session, oldest).status == QueueStatus.PENDING
        assert server_queue_manager.retry_unacknowledged_messages(db=session) == 1


def test_a_message_is_retried_once_not_once_per_sweep(session):
    host = _host(session)
    message_id = _sent(session, host)
    assert server_queue_manager.retry_unacknowledged_messages(db=session) == 1
    assert server_queue_manager.retry_unacknowledged_messages(db=session) == 0
    assert _row(session, message_id).retry_count == 1


def test_a_fresh_send_is_not_swept(session):
    host = _host(session)
    message_id = _sent(session, host, minutes_ago=0)
    assert server_queue_manager.retry_unacknowledged_messages(db=session) == 0
    assert _row(session, message_id).status == QueueStatus.SENT
