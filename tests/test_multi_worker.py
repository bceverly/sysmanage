# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: several server workers sharing one database.

With ``SYSMANAGE_UVICORN_WORKERS`` > 1 every worker ran every tick, two
workers could both claim one queued message, and a worker without an agent's
WebSocket failed that agent's commands.  These pin the fixes: one leader for
the server-wide work, an atomic claim, per-host drain locks, and outbound
delivery by the worker that holds the socket.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.persistence.models import Host, MessageQueue
from backend.startup import leadership as leadership_module
from backend.startup.leadership import Leadership, check_worker_support
from backend.websocket import inbound_processor, outbound_processor
from backend.websocket.queue_manager import (
    QueueDirection,
    QueueStatus,
    server_queue_manager,
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _host(session, fqdn=None):
    host = Host(id=str(uuid4()), fqdn=fqdn or f"{uuid4().hex[:8]}.example.com",
                active=True, approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _message(session, host, direction=QueueDirection.OUTBOUND, message_type="command"):
    message = MessageQueue(
        message_id=str(uuid4()), host_id=host.id if host else None,
        direction=direction, status=QueueStatus.PENDING, priority="normal",
        message_type=message_type, message_data="{}", created_at=_now(),
    )  # fmt: skip
    session.add(message)
    session.commit()
    return message.message_id


@pytest.fixture
def workers(monkeypatch):
    def _set(count):
        monkeypatch.setenv("SYSMANAGE_UVICORN_WORKERS", str(count))

    return _set


# -- the claim -----------------------------------------------------------------


def test_a_message_is_claimed_once(session):
    message_id = _message(session, _host(session))
    assert server_queue_manager.mark_processing(message_id, db=session) is True
    assert server_queue_manager.mark_processing(message_id, db=session) is False
    session.expire_all()
    row = session.query(MessageQueue).filter_by(message_id=message_id).one()
    assert row.status == QueueStatus.IN_PROGRESS
    assert row.started_at is not None


def test_a_missing_message_is_not_claimed(session):
    assert server_queue_manager.mark_processing("no-such", db=session) is False


# -- leader election -----------------------------------------------------------


def _engine(dialect):
    engine = MagicMock()
    engine.dialect.name = dialect
    return engine


async def test_without_advisory_locks_the_process_leads():
    lead = Leadership()
    await lead.start(_engine("sqlite"))
    assert lead.is_leader
    ran = []

    async def work():
        ran.append(True)

    await lead.singleton(work())
    assert ran == [True]


async def test_a_follower_waits_then_takes_over():
    lead = Leadership()
    answers = iter([False, True])
    with patch.object(Leadership, "_try_acquire", lambda self: next(answers)):
        await lead.start(_engine("postgresql"))
        assert not lead.is_leader
        ran = []

        async def work():
            ran.append(True)

        task = lead.singleton(work())
        await asyncio.sleep(0)
        assert ran == []  # waiting for leadership
        await lead._check()  # pylint: disable=protected-access
        await task
    assert lead.is_leader and ran == [True]
    await lead.stop()


async def test_a_waiting_task_cancels_cleanly():
    lead = Leadership()
    with patch.object(Leadership, "_try_acquire", lambda self: False):
        await lead.start(_engine("postgresql"))

        async def work():
            raise AssertionError("must not run")

        task = lead.singleton(work())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await lead.stop()


async def test_a_leader_that_lost_its_lock_shuts_itself_down():
    lead = Leadership()
    acquire = iter([True, False])
    with (
        patch.object(Leadership, "_try_acquire", lambda self: next(acquire)),
        patch.object(Leadership, "_still_held", lambda self: False),
        patch.object(leadership_module.os, "kill") as kill,
    ):
        await lead.start(_engine("postgresql"))
        assert lead.is_leader
        await lead._check()  # pylint: disable=protected-access
    kill.assert_called_once()
    await lead.stop()


async def test_a_leader_whose_connection_dropped_takes_the_lock_back():
    lead = Leadership()
    with (
        patch.object(Leadership, "_try_acquire", lambda self: True),
        patch.object(Leadership, "_still_held", lambda self: False),
        patch.object(leadership_module.os, "kill") as kill,
    ):
        await lead.start(_engine("postgresql"))
        await lead._check()  # pylint: disable=protected-access
    kill.assert_not_called()
    assert lead.is_leader
    await lead.stop()


async def test_stop_closes_the_lock_connection_for_good():
    lead = Leadership()
    conn = MagicMock()

    def take(self):
        self._conn = conn  # pylint: disable=protected-access
        return True

    with patch.object(Leadership, "_try_acquire", take):
        await lead.start(_engine("postgresql"))
    await lead.stop()
    conn.invalidate.assert_called_once()  # not returned to the pool, lock and all


def test_several_workers_need_postgresql(workers):
    workers(2)
    with pytest.raises(RuntimeError, match="needs PostgreSQL"):
        check_worker_support(_engine("sqlite"))
    check_worker_support(_engine("postgresql"))
    workers(1)
    check_worker_support(_engine("sqlite"))


# -- the inbound drain ---------------------------------------------------------


def test_host_locks_are_a_no_op_for_one_process(session, workers):
    workers(1)
    locks = inbound_processor._HostLocks(session)  # pylint: disable=protected-access
    assert not locks.active
    assert locks.acquire("any-host")
    locks.release("any-host")
    locks.close()


def test_host_locks_use_postgresql_advisory_locks(workers):
    workers(4)
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = False
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.get_bind.return_value.connect.return_value.execution_options.return_value = conn
    locks = inbound_processor._HostLocks(db)  # pylint: disable=protected-access
    assert locks.active
    assert locks.acquire("host-a") is False
    assert "pg_try_advisory_lock" in str(conn.execute.call_args[0][0])
    locks.close()
    assert "pg_advisory_unlock_all" in str(conn.execute.call_args[0][0])
    conn.close.assert_called_once()


async def test_a_host_locked_by_another_worker_is_skipped(session):
    host = _host(session)
    _message(session, host, QueueDirection.INBOUND, message_type="heartbeat")
    deadline = asyncio.get_running_loop().time() + 5
    with (
        patch.object(inbound_processor._HostLocks, "acquire", return_value=False),
        patch.object(inbound_processor, "_drain_one_host") as drain,
        patch.object(inbound_processor.time, "monotonic", return_value=0.0),
    ):
        more = await inbound_processor._drain_host_queues(session, deadline)
    drain.assert_not_called()
    assert more is False


def test_another_workers_in_progress_message_is_left_alone(session, workers):
    host = _host(session)
    message = MessageQueue(
        message_id=str(uuid4()), host_id=host.id, direction=QueueDirection.INBOUND,
        status=QueueStatus.IN_PROGRESS, priority="normal", message_type="heartbeat",
        message_data="{}", created_at=_now(), started_at=_now() - timedelta(seconds=90),
    )  # fmt: skip
    session.add(message)
    session.commit()
    workers(4)
    inbound_processor._reset_stuck_messages(session)
    session.expire_all()
    assert session.get(MessageQueue, message.id).status == QueueStatus.IN_PROGRESS
    workers(1)
    inbound_processor._reset_stuck_messages(session)
    session.expire_all()
    assert session.get(MessageQueue, message.id).status == QueueStatus.PENDING


async def test_host_less_messages_are_the_leaders(session, workers):
    workers(4)
    with (
        patch.object(inbound_processor, "_drain_host_queues", return_value=False),
        patch.object(inbound_processor, "_drain_null_host_messages") as null_drain,
        patch.object(inbound_processor.leadership, "_event", None),
    ):
        await inbound_processor.process_pending_messages(session)
    null_drain.assert_not_called()


# -- outbound ------------------------------------------------------------------


async def test_outbound_takes_only_this_workers_agents(session, workers):
    mine = _host(session, "mine.example.com")
    theirs = _host(session, "theirs.example.com")
    _message(session, mine)
    _message(session, theirs)
    workers(4)
    with (
        patch.object(outbound_processor, "local_hostnames", return_value=["mine.example.com"]),
        patch.object(outbound_processor, "process_outbound_message") as send,
    ):  # fmt: skip
        await outbound_processor.process_outbound_messages(session)
    assert [call.args[1].fqdn for call in send.call_args_list] == ["mine.example.com"]


async def test_outbound_with_no_local_agents_touches_nothing(session, workers):
    _message(session, _host(session))
    workers(4)
    with (
        patch.object(outbound_processor, "local_hostnames", return_value=[]),
        patch.object(outbound_processor, "process_outbound_message") as send,
    ):
        await outbound_processor.process_outbound_messages(session)
    send.assert_not_called()


async def test_one_worker_still_takes_every_host(session, workers):
    _message(session, _host(session))
    _message(session, _host(session))
    workers(1)
    with patch.object(outbound_processor, "process_outbound_message") as send:
        await outbound_processor.process_outbound_messages(session)
    assert send.call_count == 2


def test_local_hostnames_are_lower_cased():
    from backend.websocket.connection_manager import connection_manager

    with patch.dict(connection_manager.hostname_to_agent, {"Web-01.Example.com": "a"}):
        names = outbound_processor.local_hostnames()
    assert names.count("web-01.example.com") == 1


# -- counting the processes ------------------------------------------------------


def test_counted_processes_count_even_without_the_env_var(workers):
    """`uvicorn --workers 4` (or a second server) never sets the env var."""
    workers(1)
    with patch.object(leadership_module.leadership, "members", 3):
        assert leadership_module.multi_process()
    assert not leadership_module.multi_process()


async def test_a_failed_count_keeps_the_last_one():
    lead = Leadership()
    lead.members = 4

    def boom(self):
        raise RuntimeError("database away")

    with patch.object(Leadership, "_count_members", boom):
        await lead._refresh_members()  # pylint: disable=protected-access
    assert lead.members == 4


def test_counting_joins_once_and_rejoins_after_a_dropped_connection():
    lead = Leadership()
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = 2
    engine = _engine("postgresql")
    engine.connect.return_value.execution_options.return_value = conn
    lead._engine = engine  # pylint: disable=protected-access
    assert lead._count_members() == 2  # pylint: disable=protected-access
    assert lead._count_members() == 2  # pylint: disable=protected-access
    assert engine.connect.call_count == 1
    conn.execute.side_effect = RuntimeError("gone")
    with pytest.raises(RuntimeError):
        lead._count_members()  # pylint: disable=protected-access
    assert lead._member_conn is None  # pylint: disable=protected-access
