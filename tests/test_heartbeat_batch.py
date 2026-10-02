# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: heartbeats batched instead of a row write each.

At 10,000 agents every heartbeat loading and rewriting its host row was ~333
write transactions a second on the WebSocket path; worker pools ran dry.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.api.message_handlers_core import handle_heartbeat
from backend.persistence.models import Host
from backend.websocket import heartbeat_batch as hb

BEAT = {"is_privileged": True, "enabled_shells": ["bash"], "agent_version": "3.10",
        "public_ip": None}  # fmt: skip


@pytest.fixture(autouse=True)
def _clean():
    hb._pending.clear()  # pylint: disable=protected-access
    yield
    hb._pending.clear()  # pylint: disable=protected-access


def _host(session, last_access=None, status="up"):
    host = Host(id=uuid4(), fqdn=f"{uuid4().hex[:8]}.example.com", active=True,
                approval_status="approved", status=status, last_access=last_access)  # fmt: skip
    session.add(host)
    session.commit()
    return host


def _connection(host):
    return SimpleNamespace(host_id=host.id, hostname=host.fqdn, ipv4="10.0.0.1",
                           ipv6=None, send_message=AsyncMock())  # fmt: skip


def _beat(host, **changes):
    return {**BEAT, "host_id": str(host.id), "message_id": "m", **changes}


async def test_the_first_heartbeat_takes_the_full_path_then_identical_ones_batch(
    session,
):
    host = _host(session)
    conn = _connection(host)
    with patch.object(hb, "note") as note:
        await handle_heartbeat(session, conn, _beat(host))
        note.assert_not_called()  # first: the full path (row write)
        await handle_heartbeat(session, conn, _beat(host))
    note.assert_called_once()
    assert conn.send_message.await_count == 2  # acked either way


async def test_a_changed_field_takes_the_full_path_again(session):
    host = _host(session)
    conn = _connection(host)
    await handle_heartbeat(session, conn, _beat(host))
    with patch.object(hb, "note") as note:
        await handle_heartbeat(session, conn, _beat(host, agent_version="3.11"))
    note.assert_not_called()
    session.expire_all()
    assert session.get(Host, host.id).agent_version == "3.11"


def test_a_queued_heartbeat_is_never_batched():
    conn = SimpleNamespace(
        is_mock_connection=True, heartbeat_fingerprint=hb.fingerprint(BEAT)
    )
    assert not hb.can_batch(conn, BEAT)


def test_a_flush_writes_seen_time_and_brings_a_down_host_back_up(session):
    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    host = _host(session, last_access=stale, status="down")
    hb._pending[str(host.id)] = (session.get_bind(),  # pylint: disable=protected-access
                                 datetime.now(timezone.utc).replace(tzinfo=None))  # fmt: skip
    assert hb.flush() == 1
    session.expire_all()
    row = session.get(Host, host.id)
    assert row.last_access > stale and row.status == "up" and row.active
    assert hb.flush() == 0  # nothing left


def test_a_host_deleted_meanwhile_does_not_poison_the_batch(session):
    host = _host(session)
    engine = session.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    hb._pending[str(uuid4())] = (engine, now)  # pylint: disable=protected-access
    hb._pending[str(host.id)] = (engine, now)  # pylint: disable=protected-access
    hb.flush()
    session.expire_all()
    assert session.get(Host, host.id).last_access == now
    assert not hb._pending  # pylint: disable=protected-access


def test_a_failed_write_is_kept_for_the_next_flush(session):
    host = _host(session)
    hb._pending[str(host.id)] = (
        session.get_bind(),
        datetime.now(),
    )  # pylint: disable=protected-access
    with patch.object(hb, "sessionmaker", side_effect=RuntimeError("db away")):
        assert hb.flush() == 0
    assert str(host.id) in hb._pending  # pylint: disable=protected-access
