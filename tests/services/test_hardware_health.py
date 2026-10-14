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
