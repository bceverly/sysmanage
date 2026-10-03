# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: the indexes the 10,000-agent run found missing.

pg_stat_statements (2026-10-02): reading one host's software inventory took
61 ms (no index on host_id: every read scanned the fleet's rows) and picking
the drain's oldest waiting hosts took 61 ms (a GROUP BY over the backlog).
Together 58% of the database's time.  The migrations are run for real
(alembic, SQLite), twice, down and up again; the host order is checked on a
real database.
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.persistence.models import MessageQueue
from backend.websocket import inbound_processor
from backend.websocket.queue_enums import QueueDirection, QueueStatus

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INVENTORY = ("software_package", "user_accounts", "user_groups",
             "user_group_memberships", "host_certificates", "host_roles",
             "network_interface", "storage_device")  # fmt: skip


def _alembic(args, db_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = None
    for _attempt in range(4):  # a negative rc is a signal-kill flake
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_REPO_ROOT,
                                env=env, capture_output=True, text=True, check=False)  # fmt: skip
        if result.returncode >= 0:
            break
    assert result.returncode == 0, f"alembic {args} failed:\n{result.stderr}"


def _indexes(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()


def test_the_migrations_add_and_remove_the_indexes_idempotently():
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    wanted = {f"ix_{t}_host_id" for t in INVENTORY} | {"ix_message_queue_drain_order"}
    try:
        _alembic(["--name", "shared", "upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)
        _alembic(["upgrade", "head"], db)  # idempotent
        assert wanted <= _indexes(db)
        _alembic(["downgrade", "q26mqhostidx"], db)
        assert not wanted & _indexes(db)
        _alembic(["upgrade", "head"], db)
        assert wanted <= _indexes(db)
    finally:
        if os.path.exists(db):
            os.unlink(db)


def _queue(session, host_id, minutes_ago, **extra):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(MessageQueue(
        message_id=str(uuid4()), host_id=host_id, direction=QueueDirection.INBOUND,
        status=QueueStatus.PENDING, priority="normal", message_type="hardware_update",
        message_data="{}", created_at=now - timedelta(minutes=minutes_ago), **extra))  # fmt: skip


def _window(session, limit):
    return inbound_processor._oldest_waiting_hosts_window(  # pylint: disable=protected-access
        session, MessageQueue, limit
    )


def test_hosts_come_oldest_waiting_first(session):
    a, b, c = (str(uuid4()) for _ in range(3))
    for host, ages in ((a, (5, 1)), (b, (9, 8, 7)), (c, (3,))):
        for age in ages:
            _queue(session, host, age)
    session.commit()
    assert [str(h) for h in _window(session, 10)] == [b, a, c]
    assert [str(h) for h in _window(session, 2)] == [b, a]


def test_messages_not_due_do_not_count(session):
    a, b = str(uuid4()), str(uuid4())
    later = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
    _queue(session, a, 30, scheduled_at=later)  # retrying later
    _queue(session, a, 1)
    _queue(session, b, 10)
    _queue(session, None, 60)  # host-less: the leader's other drain
    session.commit()
    assert [str(h) for h in _window(session, 10)] == [b, a]


def test_a_flooding_host_still_comes_out_oldest_first(session, monkeypatch):
    """The read is bounded (limit x PER_HOST_LIMIT rows); hosts beyond it wait
    for a later round -- they are newer, so time order is kept."""
    monkeypatch.setattr(inbound_processor, "PER_HOST_LIMIT", 3)
    flood, late = str(uuid4()), str(uuid4())
    for age in range(100, 90, -1):
        _queue(session, flood, age)
    _queue(session, late, 1)
    session.commit()
    assert [str(h) for h in _window(session, 2)] == [flood]


def test_one_read_serves_several_rounds(session, monkeypatch):
    """The read was the database's costliest statement at 10k agents."""
    hosts = [str(uuid4()) for _ in range(6)]
    for age, host in enumerate(reversed(hosts)):
        _queue(session, host, age + 1)
    session.commit()
    reads = []
    real = (
        inbound_processor._oldest_waiting_hosts_window
    )  # pylint: disable=protected-access

    def counting(*args):
        reads.append(1)
        return real(*args)

    monkeypatch.setattr(inbound_processor, "_oldest_waiting_hosts_window", counting)
    oldest = inbound_processor._oldest_waiting_hosts  # pylint: disable=protected-access
    first, second, third = oldest(session, 2), oldest(session, 2), oldest(session, 2)
    assert [str(h) for h in first + second + third] == hosts
    assert len(reads) == 1


def test_the_window_is_read_again_when_stale(session, monkeypatch):
    host = str(uuid4())
    _queue(session, host, 5)
    session.commit()
    oldest = inbound_processor._oldest_waiting_hosts  # pylint: disable=protected-access
    clock = [1000.0]
    monkeypatch.setattr(inbound_processor.time, "monotonic", lambda: clock[0])
    assert [str(h) for h in oldest(session, 1)] == [host]
    newer = str(uuid4())
    _queue(session, newer, 1)
    session.commit()
    clock[0] += inbound_processor.HOST_WINDOW_SECONDS
    assert [str(h) for h in oldest(session, 5)] == [host, newer]


async def test_a_drained_cached_window_does_not_end_the_drain_early(
    session, monkeypatch
):
    """Hosts from an older read may be done; the drain reads again before
    deciding there is no work, so a host that arrived since is not left
    waiting for the next drain."""
    from unittest.mock import AsyncMock  # pylint: disable=import-outside-toplevel

    from backend.persistence.models import (
        Host,
    )  # pylint: disable=import-outside-toplevel

    def host(fqdn):
        row = Host(id=str(uuid4()), fqdn=fqdn, active=True, approval_status="approved")
        session.add(row)
        session.commit()
        return str(row.id)

    old, new = host("old.example.com"), host("new.example.com")
    _queue(session, new, 1)  # waiting; `old` has nothing due any more
    session.commit()
    # A fresh cached window from an earlier read that listed only `old`.
    key = inbound_processor._window_key(session)
    monkeypatch.setattr(inbound_processor, "_host_windows",
                        {key: (inbound_processor.time.monotonic(), [old])})  # fmt: skip
    processed = AsyncMock(return_value=True)
    monkeypatch.setattr(inbound_processor, "route_inbound_message", processed)
    monkeypatch.setattr(
        "backend.services.airgap_repoint_service.maybe_repoint", lambda *a: None
    )
    await inbound_processor._drain_host_queues(
        session, float("inf")
    )  # pylint: disable=protected-access
    assert processed.await_count == 1  # new's message, found by the re-read
