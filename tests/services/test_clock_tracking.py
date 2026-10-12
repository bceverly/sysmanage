# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server's measurement of a host's clock (Phase 23.3 S2): the NTP-style
arithmetic, step rejection, the median, and the rate-limited batched write."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.persistence import models
from backend.services import clock_tracking


@pytest.fixture(autouse=True)
def _clean_pending():
    clock_tracking._pending.clear()
    clock_tracking._last_prune.clear()
    yield
    clock_tracking._pending.clear()
    clock_tracking._last_prune.clear()


def _clock(t1, offset, out=0.010, back=0.010, held=0.5):
    """A clock block for a host ``offset`` seconds ahead of the server."""
    t2 = t1 + out + offset
    t3 = t2 + held
    return {"t1": t1, "t2": t2, "t3": t3, "hold": held}, t3 - offset + back


def test_offset_and_delay_from_one_exchange():
    clock, t4 = _clock(1000.0, 2.5)
    offset, delay = clock_tracking.sample_from_clock(clock, t4)
    assert offset == pytest.approx(2.5)
    assert delay == pytest.approx(0.020)


def test_queue_residence_drops_out_of_the_offset():
    clock, t4 = _clock(1000.0, -0.25, held=7.0)
    assert clock_tracking.sample_from_clock(clock, t4)[0] == pytest.approx(-0.25)


def test_asymmetric_paths_cost_at_most_half_the_difference():
    clock, t4 = _clock(1000.0, 0.0, out=0.050, back=0.010)
    assert clock_tracking.sample_from_clock(clock, t4)[0] == pytest.approx(0.020)


@pytest.mark.parametrize(
    "clock",
    [
        None,
        "x",
        {"t1": 1.0, "t2": 2.0, "t3": 3.0},
        {"t1": 1.0, "t2": 2.0, "t3": 3.0, "hold": -1.0},
        {"t1": True, "t2": 2.0, "t3": 3.0, "hold": 1.0},
        {"t1": "1", "t2": 2.0, "t3": 3.0, "hold": 1.0},
    ],
)
def test_malformed_blocks_measure_nothing(clock):
    assert clock_tracking.sample_from_clock(clock, 4.0) is None


def test_a_clock_stepped_while_the_reply_waited_is_rejected():
    clock, t4 = _clock(1000.0, 0.0, held=1.0)
    clock["hold"] = 0.2  # monotonic says 0.2 s passed, the wall clock says 1 s
    assert clock_tracking.sample_from_clock(clock, t4) is None


def test_implausible_round_trips_are_rejected():
    clock, t4 = _clock(1000.0, 0.0)
    assert clock_tracking.sample_from_clock(clock, clock["t1"] - 5) is None
    assert clock_tracking.sample_from_clock(clock, t4 + 60) is None


def test_the_figure_is_the_median_of_the_window():
    conn = SimpleNamespace()
    assert clock_tracking.current(conn) is None
    for offset in (0.100, 0.102, 0.098, 0.140, 0.101):  # one Wi-Fi stray
        clock, t4 = _clock(1000.0, offset)
        assert clock_tracking.observe(conn, clock, t4)
    figure = clock_tracking.current(conn)
    assert figure["offset_ms"] == pytest.approx(101.0)
    assert figure["rtt_ms"] == pytest.approx(20.0)
    assert figure["samples"] == 5
    assert figure["method"] == "exchange"
    for _ in range(20):
        clock, t4 = _clock(1000.0, 0.1)
        clock_tracking.observe(conn, clock, t4)
    assert clock_tracking.current(conn)["samples"] == clock_tracking.WINDOW


def test_a_refused_heartbeat_gives_a_coarse_offset_superseded_by_an_exchange():
    conn = SimpleNamespace()
    t4 = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc).timestamp()
    ahead = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc).isoformat()
    assert clock_tracking.observe_refused(conn, ahead, t4)
    figure = clock_tracking.current(conn)
    assert figure["method"] == "timestamp"
    assert figure["offset_ms"] == pytest.approx(3_600_000)
    assert figure["rtt_ms"] is None
    # A naive timestamp is UTC; a garbled one measures nothing.
    assert clock_tracking.observe_refused(conn, "2026-10-12T12:00:00", t4)
    assert not clock_tracking.observe_refused(conn, "not a time", t4)

    clock, t4 = _clock(1000.0, 0.5)
    clock_tracking.observe(conn, clock, t4)
    figure = clock_tracking.current(conn)
    assert (figure["method"], figure["samples"]) == ("exchange", 1)
    clock_tracking.observe_refused(conn, ahead, t4)
    assert clock_tracking.current(conn)["samples"] == 1  # cleared on switch


def _host(session):
    host = models.Host(
        id=uuid.uuid4(), fqdn="t480.lab", active=True, approval_status="approved"
    )
    session.add(host)
    session.commit()
    return host


def _connection(host, offset=0.25):
    conn = SimpleNamespace(host_id=str(host.id))
    clock, t4 = _clock(1000.0, offset)
    clock_tracking.observe(conn, clock, t4)
    return conn


def test_persist_writes_the_row_and_one_history_point(engine, session):
    host = _host(session)
    conn = _connection(host)
    assert clock_tracking.persist_if_due(conn, engine)  # no loop: written now
    session.expire_all()
    stored = session.get(models.Host, host.id)
    assert stored.clock_offset_ms == pytest.approx(250.0)
    assert stored.clock_rtt_ms == pytest.approx(20.0)
    assert (stored.clock_samples, stored.clock_method) == (1, "exchange")
    assert stored.clock_measured_at is not None
    samples = session.query(models.HostClockSample).all()
    assert [(s.host_id, round(s.offset_ms)) for s in samples] == [(host.id, 250)]


def test_persist_is_rate_limited_unless_the_figure_jumps(engine, session):
    host = _host(session)
    conn = _connection(host)
    assert clock_tracking.persist_if_due(conn, engine)
    assert not clock_tracking.persist_if_due(conn, engine)  # nothing new
    for _ in range(clock_tracking.WINDOW):
        clock, t4 = _clock(1000.0, 5.0)
        clock_tracking.observe(conn, clock, t4)
    assert clock_tracking.persist_if_due(conn, engine)  # moved 4.75 s
    session.expire_all()
    assert session.get(models.Host, host.id).clock_offset_ms == pytest.approx(5000.0)
    # The history point is every HISTORY_SECONDS, not every write.
    assert session.query(models.HostClockSample).count() == 1


def test_nothing_to_persist_without_a_host_figure_or_engine(engine):
    assert not clock_tracking.persist_if_due(SimpleNamespace(), engine)
    assert not clock_tracking.persist_if_due(SimpleNamespace(host_id="x"), engine)
    conn = SimpleNamespace(host_id=str(uuid.uuid4()))
    clock, t4 = _clock(1000.0, 0.0)
    clock_tracking.observe(conn, clock, t4)
    assert not clock_tracking.persist_if_due(conn, None)


def test_old_history_is_pruned(engine, session):
    host = _host(session)
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        days=clock_tracking.RETENTION_DAYS + 1
    )
    session.add(
        models.HostClockSample(
            id=uuid.uuid4(),
            host_id=host.id,
            measured_at=old,
            offset_ms=1.0,
            method="exchange",
        )
    )
    session.commit()
    clock_tracking.persist_if_due(_connection(host), engine)
    session.expire_all()
    assert [round(s.offset_ms) for s in session.query(models.HostClockSample)] == [250]


def test_a_failed_write_is_kept_for_the_next_flush(engine, session, monkeypatch):
    host = _host(session)
    conn = _connection(host)

    def boom(_engine, _rows):
        raise RuntimeError("database away")

    monkeypatch.setattr(clock_tracking, "_write", boom)
    clock_tracking.persist_if_due(conn, engine)
    assert list(clock_tracking._pending) == [str(host.id)]
    monkeypatch.undo()
    assert clock_tracking.flush() == 1
    session.expire_all()
    assert session.get(models.Host, host.id).clock_offset_ms == pytest.approx(250.0)
    assert clock_tracking.flush() == 0


def test_a_queued_history_point_survives_a_newer_figure():
    clock_tracking._pending["h"] = (object(), {"history": True})
    engine = object()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(clock_tracking, "flush", lambda: 0)
        clock_tracking._queue("h", engine, {"history": False})
    assert clock_tracking._pending["h"] == (engine, {"history": True})
