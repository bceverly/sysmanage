# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Clock bounds and statuses (Phase 23.3 S3)."""

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.persistence import models
from backend.services import clock_status, posture_evidence

NOW = datetime(2026, 10, 12, 12, 0)
BOUNDS = {"warning_ms": 1000.0, "critical_ms": 5000.0}
VERIFIED = {"reason": None, "verified": True}


def _h(offset=None, age=timedelta(minutes=1), **fields):
    measured = None if offset is None else NOW - age
    base = dict(
        clock_offset_ms=offset,
        clock_measured_at=measured,
        time_status_at=None,
        time_service_running=None,
        time_synchronized=None,
    )
    base.update(fields)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "offset, status",
    [
        (0.4, "ok"),
        (-999.9, "ok"),
        (1000.0, "warning"),
        (-4999.0, "warning"),
        (5000.0, "critical"),
        (-7_200_000.0, "critical"),
    ],
)
def test_the_offset_against_the_bounds(offset, status):
    assert clock_status.host_status(_h(offset), BOUNDS, VERIFIED, NOW) == status


def test_no_measurement_an_old_one_or_a_wrong_server_never_pass():
    status = clock_status.host_status
    assert status(_h(), BOUNDS, VERIFIED, NOW) == "unmeasured"
    old = _h(1.0, age=timedelta(hours=2))
    assert status(old, BOUNDS, VERIFIED, NOW) == "stale"
    off = {"reason": "server_off", "verified": False}
    assert status(_h(1.0), BOUNDS, off, NOW) == "server_clock_off"
    # Unreachable or no reference: judged relative to the server, flagged.
    for reason in ("unreachable", "no_reference"):
        assert status(_h(1.0), BOUNDS, {"reason": reason}, NOW) == "ok"
    for st in ("unmeasured", "stale", "server_clock_off"):
        assert clock_status.coverage_state(st) == "unknown"
    assert clock_status.coverage_state("critical") == "failing"
    assert clock_status.coverage_state("ok") == "ok"


def test_the_service_claim():
    ok = clock_status.service_ok
    assert ok(_h()) is None  # never reported
    now = NOW
    assert ok(_h(time_status_at=now, time_service_running=False)) is False
    assert ok(_h(time_status_at=now, time_synchronized=False)) is False
    both = _h(time_status_at=now, time_service_running=True, time_synchronized=True)
    assert ok(both) is True
    assert ok(_h(time_status_at=now, time_service_running=True)) is None


@pytest.mark.parametrize(
    "warning, critical, reason",
    [
        (1000, 5000, None),
        (1.0, 1.5, None),
        (5000, 1000, "warning_not_below_critical"),
        (1000, 1000, "warning_not_below_critical"),
        (0.5, 5000, "out_of_range"),
        (1000, 10**9, "out_of_range"),
        (True, 5000, "not_a_number"),
        ("1", 5000, "not_a_number"),
    ],
)
def test_bound_validation(warning, critical, reason):
    assert clock_status.valid_bounds(warning, critical) == reason


def test_server_bounds_fall_back_and_ignore_a_bad_stored_pair():
    with patch.object(clock_status.settings_service, "get_setting", return_value=None):
        assert clock_status.server_bounds()["source"] == "default"
    bad = {"warning_ms": 9000, "critical_ms": 10}
    with patch.object(clock_status.settings_service, "get_setting", return_value=bad):
        assert clock_status.server_bounds()["source"] == "default"
    good = {"warning_ms": 200, "critical_ms": 800}
    with patch.object(clock_status.settings_service, "get_setting", return_value=good):
        assert clock_status.server_bounds() == {
            "warning_ms": 200.0,
            "critical_ms": 800.0,
            "source": "server",
            "ref": "",
        }


def _host(session, **fields):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
        **fields,
    )
    session.add(host)
    session.commit()
    return host


def _tag(session, host=None):
    now = datetime.utcnow()
    tag = models.Tag(
        id=uuid.uuid4(), name=uuid.uuid4().hex[:8], created_at=now, updated_at=now
    )
    session.add(tag)
    if host is not None:
        session.add(
            models.HostTag(
                id=uuid.uuid4(), host_id=host.id, tag_id=tag.id, created_at=now
            )
        )
    session.commit()
    return tag


def test_most_specific_wins_and_the_tightest_tag(session):
    site = uuid.uuid4()
    plain = _host(session)
    sited = _host(session, site_id=site)
    tagged = _host(session, site_id=site)
    lab, dc = _tag(session, tagged).id, _tag(session, tagged).id
    idle = _tag(session).id  # a tag with bounds and no hosts
    resolver = clock_status.Resolver(session)
    assert resolver.bounds_for(plain)["source"] == "default"

    clock_status.set_override(session, "tenant", "", 2000, 8000, "admin")
    clock_status.set_override(session, "site", str(site), 500, 3000, "admin")
    clock_status.set_override(session, "tag", str(lab), 30000, 60000, "admin")
    clock_status.set_override(session, "tag", str(dc), 100, 1000, "admin")
    clock_status.set_override(session, "tag", str(idle), 1, 2, "admin")
    resolver = clock_status.Resolver(session)
    assert resolver.bounds_for(plain)["source"] == "tenant"
    assert resolver.bounds_for(sited)["source"] == "site"
    assert resolver.bounds_for(tagged)["ref"] == str(dc)  # tightest of its tags

    clock_status.set_override(session, "tenant", "", 3000, 9000, "admin")  # update
    assert [o["warning_ms"] for o in clock_status.overrides(session)][-1] == 3000.0
    assert len(clock_status.overrides(session)) == 5
    assert clock_status.clear_override(session, "tag", str(dc))
    assert not clock_status.clear_override(session, "tag", str(dc))
    assert clock_status.Resolver(session).bounds_for(tagged)["ref"] == str(lab)


def test_posture_counts_clocks(session):
    now = datetime.utcnow()
    _host(session, clock_offset_ms=2.0, clock_measured_at=now)
    _host(session, clock_offset_ms=6000.0, clock_measured_at=now)
    _host(session)
    rows = {r["coverage"]: r for r in posture_evidence._fleet_coverage(session, now)}
    assert rows["clock_sync"] == {
        "coverage": "clock_sync",
        "hosts_total": 3,
        "hosts_ok": 1,
        "hosts_failing": 1,
        "hosts_unknown": 1,
    }
