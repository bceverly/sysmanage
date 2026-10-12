# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Spot clock resync, released in waves (Phase 23.3 S5)."""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import clock_resync as cr
from backend.services import clock_tracking


def _host(session, privileged=True, offset=1330.0):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
        is_agent_privileged=privileged,
        clock_offset_ms=offset,
    )
    session.add(host)
    session.commit()
    return host


@pytest.fixture
def sent():
    """queue_command, recorded instead of queued."""
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append((str(host_id), command_type, parameters))
        return str(uuid.uuid4())

    with patch("backend.services.config_mgmt_dispatch.queue_command", side_effect=fake):
        yield calls


def test_a_request_queues_and_an_unprivileged_host_says_why(session):
    root, user = _host(session), _host(session, privileged=False)
    rows, skipped = cr.request(session, [root, user], "admin@example.com")
    assert skipped == []
    assert [(r.status, r.error) for r in rows] == [
        ("queued", None),
        ("unsupported", "not_privileged"),
    ]
    assert rows[0].offset_before_ms == 1330.0
    again, skipped = cr.request(session, [root], "admin@example.com")
    assert (again, skipped) == ([], [root])  # never doubled while active


def test_release_sends_the_servers_verified_reference(session, sent):
    host = _host(session)
    cr.request(session, [host], "admin")
    assert cr.release(session) == {"released": 1, "timed_out": 0, "failed": 0}
    assert sent == [(str(host.id), "resync_clock", {"server": "pool.ntp.org"})]
    row = session.query(models.ClockResync).one()
    assert row.status == "sent" and row.command_id and row.sent_at


def test_a_server_whose_clock_is_off_sends_no_reference(session, sent):
    cr.request(session, [_host(session)], "admin")
    with patch.object(
        cr.server_clock, "status", return_value={"verified": False, "reference": "x"}
    ):
        cr.release(session)
    assert sent[0][2] == {"server": None}


def test_waves_never_exceed_the_wave_size(session, sent):
    hosts = [_host(session) for _ in range(5)]
    cr.request(session, hosts, "admin")
    with patch.object(cr, "WAVE_SIZE", 2):
        assert cr.release(session)["released"] == 2
        assert cr.release(session)["released"] == 0  # two still in flight
        row = session.query(models.ClockResync).filter_by(status="sent").first()
        row.status = "succeeded"
        session.commit()
        assert cr.release(session)["released"] == 1


def test_a_send_with_no_result_times_out_and_frees_its_slot(session, sent):
    cr.request(session, [_host(session)], "admin")
    cr.release(session)
    later = datetime.utcnow() + cr.SENT_TIMEOUT + timedelta(minutes=1)
    assert cr.release(session, now=later)["timed_out"] == 1
    row = session.query(models.ClockResync).one()
    assert (row.status, row.error) == ("timed_out", "no_result")


def test_dispatch_failures_are_recorded(session):
    from backend.services.agent_capability_service import (  # noqa: PLC0415
        UnsupportedCapabilityError,
    )

    old, broken = _host(session), _host(session)
    cr.request(session, [old, broken], "admin")
    errors = {
        str(old.id): UnsupportedCapabilityError("resync_clock"),
        str(broken.id): RuntimeError("queue down"),
    }

    def fake(_db, host_id, _command, _params):
        raise errors[str(host_id)]

    with patch("backend.services.config_mgmt_dispatch.queue_command", side_effect=fake):
        cr.release(session)
    by_host = {
        str(r.host_id): (r.status, r.error) for r in session.query(models.ClockResync)
    }
    assert by_host[str(old.id)] == ("unsupported", "agent_too_old")
    assert by_host[str(broken.id)] == ("failed", "dispatch_failed")


def test_a_deleted_host_fails_its_resync(session, sent):
    host = _host(session)
    cr.request(session, [host], "admin")
    session.delete(host)
    session.commit()
    assert cr.release(session)["failed"] == 1


def _sent_row(session, sent):
    host = _host(session)
    cr.request(session, [host], "admin")
    cr.release(session)
    return host, session.query(models.ClockResync).one()


def test_a_success_closes_the_row_stores_the_claim_and_forgets_samples(session, sent):
    host, row = _sent_row(session, sent)
    conn = SimpleNamespace(host_id=str(host.id))
    clock_tracking.observe(conn, {"t1": 1.0, "t2": 2.3, "t3": 2.8, "hold": 0.5}, 2.0)
    manager = SimpleNamespace(active_connections={"a": conn})
    with patch("backend.websocket.connection_manager.connection_manager", manager):
        closed = cr.record_result(
            session,
            {
                "command_id": row.command_id,
                "success": True,
                "result": {
                    "service": "w32time",
                    "method": "w32tm /resync",
                    "status_after": {
                        "service": "w32time",
                        "running": True,
                        "synchronized": True,
                        "reported_offset_ms": 0.8,
                    },
                },
            },
        )
    assert (closed.status, closed.service, closed.method) == (
        "succeeded",
        "w32time",
        "w32tm /resync",
    )
    assert closed.reported_after_ms == 0.8
    session.refresh(host)
    assert host.time_service_running is True and host.time_synchronized is True
    assert clock_tracking.current(conn) is None  # the old clock is forgotten


def test_failures_keep_the_agents_code_or_its_words(session, sent):
    _host1, row = _sent_row(session, sent)
    closed = cr.record_result(
        session,
        {
            "command_id": row.command_id,
            "success": False,
            "error": "not_privileged",
            "result": {"detail": "need root"},
        },
    )
    assert (closed.status, closed.error, closed.detail) == (
        "failed",
        "not_privileged",
        "need root",
    )
    host = _host(session)
    cr.request(session, [host], "admin")
    cr.release(session)
    row2 = session.query(models.ClockResync).filter_by(host_id=host.id).one()
    closed = cr.record_result(
        session,
        {
            "command_id": row2.command_id,
            "success": False,
            "error": "Unknown command type: resync_clock (this agent is too old)",
        },
    )
    assert closed.error == "agent_error" and "Unknown command" in closed.detail


def test_a_result_for_nothing_is_ignored(session):
    assert cr.record_result(session, {"command_id": str(uuid.uuid4())}) is None
    assert cr.record_result(session, {}) is None


def test_the_tick_walks_every_host_database(session, sent):
    cr.request(session, [_host(session)], "admin")
    session.close = lambda: None  # the fixture owns it
    with patch(
        "backend.persistence.partitions.iter_host_databases",
        return_value=[("bootstrap", None, session)],
    ):
        assert cr.run_one_tick()["released"] == 1
