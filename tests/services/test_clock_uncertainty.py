# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A measurement too uncertain to judge is not judged (Phase 23.3).

2026-10-17, production: the droplet read "+4.03 s ahead, Warning" from an
exchange with an 8.06 s round trip -- the offset was exactly half the delay --
while chrony was synchronized at stratum 3 reporting -0.0 ms.  The exchange's
error is up to half its round trip, which exceeded the 1 s warning bound."""

import uuid
from collections import deque
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.persistence import models
from backend.persistence.db import Base
from backend.services import clock_status, clock_tracking

NOW = datetime(2026, 10, 17, 11, 53)
BOUNDS = {"warning_ms": 1000.0, "critical_ms": 5000.0, "source": "default", "ref": ""}
VERIFIED = {"reason": None, "verified": True}


def _host(**fields):
    base = {
        "id": uuid.uuid4(),
        "clock_offset_ms": 4030.0,
        "clock_rtt_ms": 8060.0,
        "clock_method": "exchange",
        "clock_measured_at": NOW - timedelta(minutes=1),
        "time_status_at": NOW,
        "time_service_running": True,
        "time_synchronized": True,
        "time_reported_offset_ms": -0.0,
        "site_id": None,
    }
    base.update(fields)
    return SimpleNamespace(**base)


def test_the_production_reading_is_uncertain_not_a_warning():
    assert clock_status.host_status(_host(), BOUNDS, VERIFIED, NOW) == "uncertain"


def test_the_same_offset_from_a_quick_exchange_is_a_warning():
    quick = _host(clock_rtt_ms=20.0)
    assert clock_status.host_status(quick, BOUNDS, VERIFIED, NOW) == "warning"


def test_the_coarse_timestamp_method_is_still_judged():
    coarse = _host(clock_method="timestamp", clock_rtt_ms=None, clock_offset_ms=3.6e6)
    assert clock_status.host_status(coarse, BOUNDS, VERIFIED, NOW) == "critical"


def test_nothing_is_raised_or_resynced_on_an_uncertain_reading():
    assert clock_status.clock_verdict(_host(), BOUNDS, VERIFIED, NOW) is None
    assert clock_status.coverage_state("uncertain") == "unknown"
    assert "uncertain" not in (
        clock_status.STATUS_WARNING,
        clock_status.STATUS_CRITICAL,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[models.HostClockSample.__table__, models.ClockBound.__table__],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _sample(db, host, minutes_ago, offset_ms, rtt_ms, method="exchange"):
    db.add(
        models.HostClockSample(
            id=uuid.uuid4(),
            host_id=host.id,
            measured_at=NOW - timedelta(minutes=minutes_ago),
            offset_ms=offset_ms,
            rtt_ms=rtt_ms,
            method=method,
        )
    )
    db.commit()


def _evaluate(db, hosts):
    with patch.object(
        clock_status.server_clock, "status", return_value=VERIFIED
    ), patch.object(clock_status, "server_bounds", return_value=BOUNDS):
        return clock_status.evaluate(db, hosts, NOW)


def test_the_newest_certain_sample_decides_when_the_latest_is_uncertain(db):
    host = _host()
    _sample(db, host, 20, 3.0, 12.0)  # certain, in the window
    _sample(db, host, 2, 4030.0, 8060.0)  # the uncertain one
    _server, [(_h, _b, status)] = _evaluate(db, [host])
    assert status == "ok"


def test_with_no_certain_sample_in_the_window_it_stays_uncertain(db):
    host = _host()
    _sample(db, host, 45, 3.0, 12.0)  # certain but too old
    _server, [(_h, _b, status)] = _evaluate(db, [host])
    assert status == "uncertain"


def test_the_card_explains_and_trusts_the_time_service(db):
    note = clock_status.measurement_note(db, _host(), BOUNDS, NOW)
    assert note["uncertain"] is True
    assert note["uncertainty_ms"] == pytest.approx(4030.0)
    assert note["time_service_vouches"] is True
    assert note["judged_from"] is None


def test_a_time_service_that_is_not_synchronized_does_not_vouch(db):
    note = clock_status.measurement_note(
        db, _host(time_synchronized=False), BOUNDS, NOW
    )
    assert note["time_service_vouches"] is False


# --- the measurement itself ------------------------------------------------


def test_the_four_timestamp_formula_on_the_production_exchange():
    # The server-to-agent leg took 8.06 s (the reply waited behind a busy
    # handler on the old agent); the return leg was instant; the clocks agree.
    clock = {"t1": 1000.0, "t2": 1008.06, "t3": 1010.0, "hold": 1.94}
    offset, delay = clock_tracking.sample_from_clock(clock, t4=1010.0)
    assert delay == pytest.approx(8.06)
    assert offset == pytest.approx(4.03)  # exactly half the delay: an artifact


def test_one_slow_exchange_cannot_drag_the_median():
    connection = SimpleNamespace(
        clock_state={"samples": deque(maxlen=9), "method": "exchange"}
    )
    for _ in range(4):
        connection.clock_state["samples"].append((0.002, 0.010))
    connection.clock_state["samples"].append((4.03, 8.06))
    figure = clock_tracking.current(connection)
    assert figure["offset_ms"] == pytest.approx(2.0)
    assert figure["rtt_ms"] == pytest.approx(10.0)


def test_when_every_exchange_is_slow_the_figure_says_so():
    connection = SimpleNamespace(
        clock_state={"samples": deque([(4.03, 8.06)], maxlen=9), "method": "exchange"}
    )
    figure = clock_tracking.current(connection)
    assert figure["rtt_ms"] == pytest.approx(8060.0)
    host = _host(clock_offset_ms=figure["offset_ms"], clock_rtt_ms=figure["rtt_ms"])
    assert clock_status.host_status(host, BOUNDS, VERIFIED, NOW) == "uncertain"
