# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: one queue write per inbound message, not two.

Every message was claimed (UPDATE to in-progress) and then completed (UPDATE
to completed).  A drain that holds a host exclusively -- its advisory lock,
or SQLite's single process -- needs no claim: no other worker can take that
host's messages.  Counted on the real statements sent to the database.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import event

from backend.persistence.models import Host, MessageQueue
from backend.websocket import inbound_processor
from backend.websocket.queue_enums import QueueDirection, QueueStatus


def _host(session):
    host = Host(id=str(uuid4()), fqdn=f"{uuid4().hex[:8]}.example.com",
                active=True, approval_status="approved")  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _inbound(session, host, count):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for _ in range(count):
        session.add(MessageQueue(
            message_id=str(uuid4()), host_id=host.id,
            direction=QueueDirection.INBOUND, status=QueueStatus.PENDING,
            priority="normal", message_type="hardware_update",
            message_data="{}", created_at=now))  # fmt: skip
    session.commit()


class _QueueWrites:
    """Counts UPDATEs of message_queue sent on this session's connection."""

    def __init__(self, session):
        self.engine = session.get_bind()
        self.count = 0

    def _seen(self, _conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("UPDATE MESSAGE_QUEUE"):
            self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._seen)
        return self

    def __exit__(self, *_):
        event.remove(self.engine, "before_cursor_execute", self._seen)


async def _drain(session, exclusive=None):
    patches = [
        patch.object(inbound_processor, "route_inbound_message",
                     AsyncMock(return_value=True)),
        patch("backend.services.airgap_repoint_service.maybe_repoint"),
    ]  # fmt: skip
    if exclusive is not None:
        patches.append(
            patch.object(inbound_processor._HostLocks, "exclusive", exclusive)
        )
    for active in patches:
        active.start()
    try:
        with _QueueWrites(session) as writes:
            await inbound_processor._drain_host_queues(session, float("inf"))
    finally:
        for active in patches:
            active.stop()
    session.commit()
    return writes.count


def _statuses(session):
    return {m.status for m in session.query(MessageQueue).all()}


async def test_an_exclusive_drain_writes_each_message_once(session):
    host = _host(session)
    _inbound(session, host, 5)
    assert await _drain(session) == 5  # SQLite: one process, exclusive
    assert _statuses(session) == {QueueStatus.COMPLETED}


async def test_a_shared_drain_still_claims_each_message(session):
    host = _host(session)
    _inbound(session, host, 5)
    assert await _drain(session, exclusive=False) == 10  # claim + complete
    assert _statuses(session) == {QueueStatus.COMPLETED}


async def test_a_failed_message_is_still_retried(session):
    host = _host(session)
    _inbound(session, host, 1)
    with patch.object(inbound_processor, "route_inbound_message",AsyncMock(side_effect=RuntimeError("boom"))):  # fmt: skip
        await inbound_processor._drain_host_queues(session, float("inf"))
    session.commit()
    message = session.query(MessageQueue).one()
    assert message.retry_count == 1 and message.status == QueueStatus.PENDING


def _locks(dialect, workers, monkeypatch):
    monkeypatch.setenv("SYSMANAGE_UVICORN_WORKERS", str(workers))
    db = MagicMock()
    db.get_bind.return_value.dialect.name = dialect
    return inbound_processor._HostLocks(db)


@pytest.mark.parametrize("dialect,workers,exclusive", [
    ("sqlite", 1, True),         # one process, always
    ("postgresql", 4, True),     # every worker takes the host's lock
    ("postgresql", 1, False),    # no locks: a worker joining mid-drain
])  # fmt: skip
def test_who_is_exclusive(dialect, workers, exclusive, monkeypatch):
    locks = _locks(dialect, workers, monkeypatch)
    assert locks.exclusive is exclusive
    locks.close()
