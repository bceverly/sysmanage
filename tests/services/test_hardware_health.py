# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Storing hardware health reports (Phase 23.1 S2).

The reports are shaped as the agent sends them; the drive is the lab FreeBSD
box's Crucial P1 with its 19 media errors.
"""

# pylint: disable=unbalanced-tuple-unpacking  # (event,) = one-event reports

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.api.handlers.hardware_health_handlers import (
    handle_hardware_health_update,
)
from backend.persistence import models
from backend.services import hardware_health as hh

T0 = datetime(2026, 10, 13, 12, 0, 0)


def _host(session):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
    )
    session.add(host)
    session.commit()
    return host


def _drive(state="warning", reasons=None):
    return {
        "kind": "drive",
        "id": "nvme0",
        "name": "CT1000P1SSD8",
        "state": state,
        "reasons": (
            [{"code": "media_errors", "count": 19}] if reasons is None else reasons
        ),
        "metrics": {"media_errors": 19, "percent_used": 5, "temperature_c": 39.85},
        "source": "nvmecontrol",
    }


def _sensor(state="ok", celsius=40.1):
    return {
        "kind": "sensor",
        "id": "acpi/tz0",
        "name": "ACPI tz0",
        "state": state,
        "reasons": [],
        "metrics": {"temperature_c": celsius, "critical_c": 128.1},
        "source": "sysctl",
    }


def _report(*components, failed=()):
    sources = [
        {"name": "nvmecontrol", "status": "ran"},
        {"name": "sysctl", "status": "ran"},
    ]
    sources = [
        {"name": s["name"], "status": "failed" if s["name"] in failed else "ran"}
        for s in sources
    ]
    return {"components": list(components), "sources": sources}


def _events(session, host):
    return (
        session.query(models.HardwareEvent)
        .filter(models.HardwareEvent.host_id == host.id)
        .order_by(models.HardwareEvent.occurred_at)
        .all()
    )


def test_first_report_records_only_what_is_news(session):
    host = _host(session)
    events = hh.apply_report(session, host, _report(_drive(), _sensor()), now=T0)
    session.commit()
    # the warning drive is news; the healthy sensor is not
    assert [(e.ident, e.from_state, e.to_state) for e in events] == [
        ("nvme0", None, "warning")
    ]
    assert json.loads(events[0].reasons) == [{"code": "media_errors", "count": 19}]
    assert host.hardware_state == "warning"
    assert hh.host_status(host, now=T0) == "warning"
    assert session.query(models.HardwareComponent).count() == 2


def test_an_unchanged_report_adds_nothing_and_a_change_adds_one(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_drive(), _sensor()), now=T0)
    session.commit()
    later = T0 + timedelta(minutes=15)
    # a new temperature is not a change of state
    assert not hh.apply_report(
        session, host, _report(_drive(), _sensor(celsius=45)), now=later
    )
    session.commit()
    recovered = T0 + timedelta(minutes=30)
    events = hh.apply_report(
        session, host, _report(_drive("ok", []), _sensor()), now=recovered
    )
    session.commit()
    assert [(e.from_state, e.to_state) for e in events] == [("warning", "ok")]
    row = session.query(models.HardwareComponent).filter_by(ident="nvme0").one()
    assert row.state_since == recovered
    assert row.first_seen_at == T0
    assert json.loads(row.metrics)["media_errors"] == 19
    assert hh.host_status(host, now=recovered) == "ok"


def test_a_drive_that_disappears_is_news(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_drive("ok", []), _sensor()), now=T0)
    session.commit()
    events = hh.apply_report(
        session, host, _report(_sensor()), now=T0 + timedelta(minutes=5)
    )
    session.commit()
    assert [(e.kind, e.ident, e.from_state, e.to_state) for e in events] == [
        ("drive", "nvme0", "ok", hh.GONE)
    ]
    assert session.query(models.HardwareComponent).filter_by(ident="nvme0").count() == 0


def test_a_failed_source_keeps_what_it_reported_last_time(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_drive(), _sensor()), now=T0)
    session.commit()
    # nvmecontrol failed this time: the drive is not "gone"
    events = hh.apply_report(
        session, host, _report(_sensor(), failed=("nvmecontrol",)),
        now=T0 + timedelta(minutes=5),
    )  # fmt: skip
    session.commit()
    assert not events
    assert session.query(models.HardwareComponent).filter_by(ident="nvme0").count() == 1
    sources = json.loads(host.hardware_sources)
    assert {"name": "nvmecontrol", "status": "failed"} in sources


def test_a_healthy_sensor_vanishes_quietly_a_hot_one_does_not(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_sensor()), now=T0)
    session.commit()
    assert not hh.apply_report(session, host, _report(), now=T0 + timedelta(minutes=1))
    session.commit()
    hh.apply_report(
        session, host, _report(_sensor("warning", 99.0)), now=T0 + timedelta(minutes=2)
    )
    session.commit()
    events = hh.apply_report(session, host, _report(), now=T0 + timedelta(minutes=3))
    assert [(e.from_state, e.to_state) for e in events] == [("warning", hh.GONE)]


def test_reports_are_validated_and_capped(session):
    host = _host(session)
    long_name = "x" * 1000
    report = {
        "components": [
            {"kind": "toaster", "id": "t0", "state": "ok"},  # unknown kind
            {"kind": "drive", "id": "d0", "state": "on fire"},  # unknown state
            {"kind": "drive", "state": "ok"},  # no id
            "not a component",
            {
                "kind": "drive", "id": "sda", "name": long_name, "state": "failed",
                "reasons": [{"code": "smart_failed"}, "nope", {"no": "code"},
                            {"code": "x", "nested": {"a": 1}, "list": [1, {"b": 2}]}],
                "metrics": {"ok": 1, "nested": {"a": 1}, "list": [1]},
            },  # fmt: skip
            {"kind": "drive", "id": "sda", "state": "ok"},  # duplicate: ignored
        ],
        "sources": [
            {"name": "smartctl", "status": "ran"},
            {"name": "x", "status": "?"},
        ],
    }
    hh.apply_report(session, host, report, now=T0)
    session.commit()
    (row,) = session.query(models.HardwareComponent).filter_by(host_id=host.id).all()
    assert row.ident == "sda" and row.state == "failed"
    assert len(row.name) == 255
    assert json.loads(row.reasons) == [
        {"code": "smart_failed"},
        {"code": "x", "nested": None, "list": [1]},
    ]
    assert json.loads(row.metrics) == {"ok": 1}
    assert json.loads(host.hardware_sources) == [{"name": "smartctl", "status": "ran"}]
    # garbage in place of lists is "nothing reported", never an error
    hh.apply_report(session, host, {"components": "x", "sources": 7}, now=T0)
    assert host.hardware_state == "unknown"


def test_host_status_is_never_ok_without_a_recent_report(session):
    host = _host(session)
    assert hh.host_status(host, now=T0) == "unmeasured"
    hh.apply_report(session, host, _report(_sensor()), now=T0)
    assert hh.host_status(host, now=T0 + timedelta(minutes=59)) == "ok"
    assert hh.host_status(host, now=T0 + timedelta(minutes=61)) == "stale"
    hh.apply_report(session, host, _report(), now=T0)
    assert hh.host_status(host, now=T0) == "unknown"


def test_acknowledge_and_resolve(session):
    host = _host(session)
    (event,) = hh.apply_report(session, host, _report(_drive()), now=T0)
    session.commit()
    acked = hh.acknowledge(session, str(event.id), "admin@example.com", "replacing it")
    assert acked.acknowledged_by == "admin@example.com" and acked.note == "replacing it"
    first = acked.acknowledged_at
    assert (
        hh.acknowledge(session, str(event.id), "other@example.com").acknowledged_at
        == first
    )
    resolved = hh.resolve(session, str(event.id), "admin@example.com")
    assert resolved.resolved_by == "admin@example.com"
    assert hh.acknowledge(session, "not-a-uuid", "x") is None
    assert hh.resolve(session, str(uuid.uuid4()), "x") is None


def test_resolve_also_acknowledges(session):
    host = _host(session)
    (event,) = hh.apply_report(session, host, _report(_drive()), now=T0)
    session.commit()
    resolved = hh.resolve(session, str(event.id), "admin@example.com", "x" * 900)
    assert resolved.acknowledged_at == resolved.resolved_at
    assert len(resolved.note) == 500


def test_views_worst_first(session):
    host = _host(session)
    failing = dict(_drive("failed", [{"code": "smart_failed"}]), id="sdb")
    # now, not T0: the view judges freshness against the real clock
    hh.apply_report(session, host, _report(_sensor(), _drive(), failing))
    session.commit()
    view = hh.host_view(session, host)
    assert [c["id"] for c in view["components"]] == ["sdb", "nvme0", "acpi/tz0"]
    assert view["status"] == "failed"
    assert {e["component_id"] for e in view["events"]} == {"sdb", "nvme0"}
    counts = hh.counts_by_host(session, [host.id])[str(host.id)]
    assert counts == {"ok": 1, "warning": 1, "failed": 1}
    problems = hh.problems_by_host(session, [host.id])[str(host.id)]
    assert [p["id"] for p in problems] == ["sdb", "nvme0"]
    assert hh.counts_by_host(session, []) == {}


def test_the_handler(session):
    host = _host(session)
    connection = SimpleNamespace(host_id=host.id)
    result = asyncio.run(
        handle_hardware_health_update(
            session, connection, {"data": _report(_drive(), _sensor())}
        )
    )
    assert result["message_type"] == "success"
    assert result["data"] == {"state": "warning", "events": 1}
    missing = asyncio.run(
        handle_hardware_health_update(session, SimpleNamespace(), {"data": {}})
    )
    assert missing["error_type"] == "host_not_registered"
    unknown = asyncio.run(
        handle_hardware_health_update(
            session, SimpleNamespace(host_id=uuid.uuid4()), {"data": {}}
        )
    )
    assert unknown["error_type"] == "host_not_registered"


def test_a_triggered_report_records_the_evidence(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_drive("ok", []), _sensor()), now=T0)
    session.commit()
    report = _report(_drive("ok", []), _sensor())
    report["trigger"] = "event"
    report["evidence"] = [
        {"source": "kernel", "category": "storage",
         "text": "Buffer I/O error on dev dm-1, logical block 0, async page read"},
        {"source": "kernel", "category": "storage",
         "text": "Buffer I/O error on dev dm-1, logical block 1, async page read"},
        {"source": "kernel", "category": "memory", "text": "mce: [Hardware Error]: CPU 0"},
        {"source": "kernel", "category": "plumbing", "text": "not a category"},
        {"source": "kernel", "category": "storage", "text": ""},
        "junk",
    ]  # fmt: skip
    # no component changed state -- the I/O errors are news on their own
    events = hh.apply_report(session, host, report, now=T0 + timedelta(minutes=1))
    session.commit()
    by_ident = {e.ident: e for e in events}
    assert set(by_ident) == {"storage", "memory"}
    storage = by_ident["storage"]
    assert (storage.kind, storage.from_state, storage.to_state) == (
        hh.SYSTEM,
        None,
        "warning",
    )
    reasons = json.loads(storage.reasons)
    assert [r["code"] for r in reasons] == ["os_storage_event", "os_storage_event"]
    assert reasons[0]["source"] == "kernel" and "logical block 0" in reasons[0]["text"]
    assert json.loads(by_ident["memory"].reasons)[0]["code"] == "os_memory_event"
    # evidence never becomes a component
    assert (
        session.query(models.HardwareComponent).filter_by(host_id=host.id).count() == 2
    )


def _coretemp(celsius, state):
    return {
        "kind": "sensor",
        "id": "coretemp/temp1",
        "name": "coretemp Package id 0",
        "state": state,
        "reasons": (
            [{"code": "temperature_high", "value": celsius, "limit": 84.0}]
            if state == "warning"
            else []
        ),
        "metrics": {"temperature_c": celsius, "high_c": 84.0, "critical_c": 100.0},
        "source": "hwmon",
    }


def test_a_sensor_hovering_at_its_limit_does_not_flap(session):
    """A lid-closed laptop idling at its "high" mark used to log Warning <->
    Healthy on every report (nextcloud, dozens a night, 2026-10-19)."""
    host = _host(session)
    readings = [
        (86, "warning"),
        (83, "ok"),
        (85, "warning"),
        (82, "ok"),
        (84, "warning"),
    ]
    for minute, (celsius, state) in enumerate(readings):
        hh.apply_report(
            session,
            host,
            _report(_coretemp(celsius, state)),
            T0 + timedelta(minutes=minute),
        )
        session.commit()
    (event,) = _events(session, host)  # the one real crossing, nothing after
    assert event.to_state == "warning"
    assert host.hardware_state == "warning"
    row = session.query(models.HardwareComponent).one()
    assert json.loads(row.reasons)[0]["code"] == "temperature_high"


def test_a_sensor_clears_once_it_cools_past_the_band(session):
    host = _host(session)
    hh.apply_report(session, host, _report(_coretemp(86, "warning")), T0)
    session.commit()
    hh.apply_report(
        session, host, _report(_coretemp(79, "ok")), T0 + timedelta(minutes=1)
    )
    session.commit()
    first, second = _events(session, host)
    assert (first.to_state, second.to_state) == ("warning", "ok")
    assert host.hardware_state == "ok"


def test_hysteresis_never_holds_a_drive_or_a_sensor_without_a_limit(session):
    host = _host(session)
    hh.apply_report(
        session, host, _report(_drive("warning"), _sensor("warning", 90)), T0
    )
    session.commit()
    hh.apply_report(
        session,
        host,
        _report(_drive("ok", []), _sensor("ok", 89)),
        T0 + timedelta(minutes=1),
    )
    session.commit()
    assert {r.state for r in session.query(models.HardwareComponent)} == {"ok"}


def _hot_host(session, limit):
    host = _host(session)
    host.hardware_temp_warning_c = limit
    session.commit()
    return host


def _state_after(session, host, *readings):
    """Report each (celsius, agent_state) in turn; the stored row after."""
    for minute, (celsius, state) in enumerate(readings):
        hh.apply_report(
            session,
            host,
            _report(_coretemp(celsius, state)),
            T0 + timedelta(minutes=minute),
        )
        session.commit()
    return session.query(models.HardwareComponent).one()


def test_a_host_limit_above_the_device_limit_quiets_a_hot_laptop(session):
    """nextcloud idles at 85-90 C with the lid closed; its owner sets 95 C."""
    host = _hot_host(session, 95.0)
    row = _state_after(session, host, (90, "warning"))
    assert row.state == "ok"
    assert not _events(session, host)
    metrics = json.loads(row.metrics)
    assert metrics["high_c"] == 95.0
    assert metrics["device_high_c"] == 84.0
    assert metrics["high_source"] == "host"
    row = _state_after(session, host, (96, "warning"))
    assert row.state == "warning"
    assert json.loads(row.reasons) == [
        {"code": "temperature_high", "value": 96, "limit": 95.0}
    ]


def test_a_host_limit_below_the_device_limit_warns_earlier(session):
    host = _hot_host(session, 70.0)
    row = _state_after(session, host, (75, "ok"))
    assert row.state == "warning"
    assert host.hardware_state == "warning"


def test_the_device_critical_limit_still_fails_whatever_the_host_limit(session):
    host = _hot_host(session, 120.0)
    hot = _coretemp(101, "failed")
    hot["reasons"] = [{"code": "temperature_critical", "value": 101, "limit": 100.0}]
    hh.apply_report(session, host, _report(hot), T0)
    session.commit()
    assert session.query(models.HardwareComponent).one().state == "failed"
    # an agent that only said "warning" at 100 C is still judged critical
    later = hh.apply_report(
        session, host, _report(_coretemp(100, "warning")), T0 + timedelta(minutes=1)
    )
    session.commit()
    assert not later  # still failed: no change, no event
    assert session.query(models.HardwareComponent).one().state == "failed"


def test_hysteresis_uses_the_host_limit(session):
    host = _hot_host(session, 90.0)
    row = _state_after(session, host, (91, "warning"), (87, "warning"))
    assert row.state == "warning"  # 87 is inside the 5 C band below 90
    row = _state_after(session, host, (84, "warning"))
    assert row.state == "ok"


def test_a_cleared_limit_falls_back_to_the_device_limit(session):
    host = _hot_host(session, 95.0)
    _state_after(session, host, (90, "warning"))
    host.hardware_temp_warning_c = None
    session.commit()
    row = _state_after(session, host, (90, "warning"))
    assert row.state == "warning"
    assert "high_source" not in json.loads(row.metrics)


def test_the_host_limit_leaves_drives_and_non_temperature_reasons_alone():
    from backend.services import hardware_temperature_limit as tl

    drive = hh.clean_component(_drive("warning"))
    assert tl.apply_limit(drive, 95.0) is drive
    fan = hh.clean_component(
        dict(_sensor("warning", 50), reasons=[{"code": "fan_stopped"}])
    )
    assert tl.apply_limit(fan, 95.0) is fan
    assert (
        tl.apply_limit(hh.clean_component(_coretemp(90, "warning")), None)["state"]
        == "warning"
    )
    assert tl.valid_limit(None) and tl.valid_limit(30) and tl.valid_limit(125.0)
    assert (
        not tl.valid_limit(29.9)
        and not tl.valid_limit(126)
        and not tl.valid_limit(True)
    )
