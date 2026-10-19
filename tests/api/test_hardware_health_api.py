# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Hardware health endpoints (Phase 23.1 S2)."""

import json
import uuid
from unittest.mock import patch

from backend.persistence import models
from backend.services import hardware_health


def _host(session, fqdn):
    host = models.Host(
        id=uuid.uuid4(), fqdn=fqdn, active=True, approval_status="approved"
    )
    session.add(host)
    session.commit()
    return host


def _report(state, ident="nvme0"):
    return {
        "components": [
            {
                "kind": "drive",
                "id": ident,
                "name": "CT1000P1SSD8",
                "state": state,
                "reasons": (
                    [] if state == "ok" else [{"code": "media_errors", "count": 19}]
                ),
                "metrics": {"media_errors": 19},
                "source": "nvmecontrol",
            }
        ],
        "sources": [{"name": "nvmecontrol", "status": "ran"}],
    }


def _seed(session):
    bad = _host(session, "freebsd.lab")
    good = _host(session, "beast.lab")
    silent = _host(session, "never.lab")
    hardware_health.apply_report(session, bad, _report("warning"))
    hardware_health.apply_report(session, good, _report("ok"))
    session.commit()
    return bad, good, silent


def test_fleet_worst_first_and_never_ok_unmeasured(client, auth_headers, session):
    bad, good, silent = _seed(session)
    body = client.get("/api/v1/hardware-health/hosts", headers=auth_headers).json()
    order = [h["fqdn"] for h in body["hosts"]]
    assert (
        order.index("freebsd.lab") < order.index("never.lab") < order.index("beast.lab")
    )
    by_name = {h["fqdn"]: h for h in body["hosts"]}
    assert by_name["never.lab"]["status"] == "unmeasured"
    assert by_name["freebsd.lab"]["component_counts"] == {"warning": 1}
    assert by_name["freebsd.lab"]["problems"][0]["reasons"] == [
        {"code": "media_errors", "count": 19}
    ]
    assert body["counts"]["warning"] >= 1
    summary = client.get("/api/v1/hardware-health/summary", headers=auth_headers).json()
    assert summary["counts"]["unmeasured"] >= 1
    assert {str(bad.id), str(good.id), str(silent.id)} <= {
        h["host_id"] for h in body["hosts"]
    }


def test_host_view(client, auth_headers, session):
    bad, _good, _silent = _seed(session)
    body = client.get(
        f"/api/v1/host/{bad.id}/hardware-health", headers=auth_headers
    ).json()
    assert body["status"] == "warning"
    assert body["components"][0]["id"] == "nvme0"
    assert body["sources"] == [{"name": "nvmecontrol", "status": "ran"}]
    assert [e["to_state"] for e in body["events"]] == ["warning"]
    for host_id in (uuid.uuid4(), "nope"):
        response = client.get(
            f"/api/v1/host/{host_id}/hardware-health", headers=auth_headers
        )
        assert response.status_code == 404


def test_events_acknowledge_and_resolve(client, auth_headers, session):
    bad, _good, _silent = _seed(session)
    events = client.get(
        "/api/v1/hardware-health/events", params={"open": "true"}, headers=auth_headers
    ).json()["events"]
    (event,) = [e for e in events if e["host_id"] == str(bad.id)]
    assert event["fqdn"] == "freebsd.lab"
    acked = client.post(
        f"/api/v1/hardware-health/events/{event['id']}/acknowledge",
        json={"note": "replacement ordered"},
        headers=auth_headers,
    ).json()
    assert acked["acknowledged_at"] and acked["note"] == "replacement ordered"
    resolved = client.post(
        f"/api/v1/hardware-health/events/{event['id']}/resolve",
        json={},
        headers=auth_headers,
    ).json()
    assert resolved["resolved_at"]
    still_open = client.get(
        "/api/v1/hardware-health/events",
        params={"open": "true", "host_id": str(bad.id)},
        headers=auth_headers,
    ).json()["events"]
    assert not still_open
    missing = client.post(
        f"/api/v1/hardware-health/events/{uuid.uuid4()}/resolve",
        json={},
        headers=auth_headers,
    )
    assert missing.status_code == 404


def test_changing_events_needs_the_role(client, auth_headers, session):
    bad, _good, _silent = _seed(session)
    (event,) = hardware_health.host_view(session, bad)["events"]
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        response = client.post(
            f"/api/v1/hardware-health/events/{event['id']}/acknowledge",
            json={},
            headers=auth_headers,
        )
    assert response.status_code == 403


def _unreadable(session, fqdn):
    host = _host(session, fqdn)
    report = _report("warning", ident="ada0")
    report["components"][0].update(
        state="unknown", reasons=[{"code": "smartctl_absent"}], source=None
    )
    hardware_health.apply_report(session, host, report)
    session.commit()
    return host


def test_smartmontools_recommended_and_installed(client, auth_headers, session):
    needs = _unreadable(session, "freebsd.lab")
    bad, _good, _silent = _seed(session)
    body = client.get(
        "/api/v1/hardware-health/smartmontools", headers=auth_headers
    ).json()
    assert [h["fqdn"] for h in body["hosts"]] == ["freebsd.lab"]
    assert body["auto"] is False and body["hosts"][0]["install"] is None
    view = client.get(f"/api/v1/host/{needs.id}/hardware-health", headers=auth_headers)
    assert view.json()["smartmontools"] == {"recommended": True, "install": None}
    with patch(
        "backend.services.smartmontools_install.config_mgmt_dispatch.queue_command",
        return_value="cmd-1",
    ) as queue:
        response = client.post(
            "/api/v1/hardware-health/smartmontools/install",
            json={"host_ids": [str(needs.id), str(bad.id)]},
            headers=auth_headers,
        )
    assert response.json() == {"queued": 1, "skipped": 1}  # bad needs no smartctl
    assert queue.call_args.args[3] == {"plan": {"packages": ["smartmontools"]}}
    view = client.get(f"/api/v1/host/{needs.id}/hardware-health", headers=auth_headers)
    assert view.json()["smartmontools"]["install"]["status"] == "queued"


def test_smartmontools_install_needs_both_roles(client, auth_headers, session):
    needs = _unreadable(session, "freebsd.lab")
    with patch(
        "backend.persistence.models.User.has_role",
        side_effect=lambda role: role.value != "Add Package",
        create=True,
    ):
        response = client.post(
            "/api/v1/hardware-health/smartmontools/install",
            json={"host_ids": [str(needs.id)]},
            headers=auth_headers,
        )
    assert response.status_code == 403


def test_automatic_install_is_licensed_and_consented(client, auth_headers, session):
    with patch("backend.services.smartmontools_install.licensed", return_value=False):
        response = client.put(
            "/api/v1/hardware-health/smartmontools",
            json={"auto": True},
            headers=auth_headers,
        )
    assert response.status_code == 402
    with patch(
        "backend.services.smartmontools_install.licensed", return_value=True
    ), patch(
        "backend.services.smartmontools_install.set_auto", return_value=True
    ) as set_auto:
        response = client.put(
            "/api/v1/hardware-health/smartmontools",
            json={"auto": True},
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    set_auto.assert_called_once_with(None, True)


def test_a_host_temperature_limit_is_set_shown_audited_and_cleared(
    client, auth_headers, session
):
    host = _host(session, "nextcloud.lab")
    url = f"/api/v1/host/{host.id}/hardware-health/temperature-limit"
    response = client.put(url, json={"limit_c": 95}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"temperature_limit_c": 95.0}
    view = client.get(f"/api/v1/host/{host.id}/hardware-health", headers=auth_headers)
    assert view.json()["temperature_limit_c"] == 95.0
    session.expire_all()
    audit = (
        session.query(models.AuditLog)
        .filter(models.AuditLog.entity_id == str(host.id))
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert audit is not None and "95" in audit.description
    cleared = client.put(url, json={"limit_c": None}, headers=auth_headers)
    assert cleared.json() == {"temperature_limit_c": None}
    session.expire_all()
    assert session.get(models.Host, host.id).hardware_temp_warning_c is None


def test_a_host_temperature_limit_is_range_checked(client, auth_headers, session):
    host = _host(session, "mail.lab")
    url = f"/api/v1/host/{host.id}/hardware-health/temperature-limit"
    for bad in (29, 126, -5):
        response = client.put(url, json={"limit_c": bad}, headers=auth_headers)
        assert response.status_code == 422
    session.expire_all()
    assert session.get(models.Host, host.id).hardware_temp_warning_c is None
    missing = client.put(
        f"/api/v1/host/{uuid.uuid4()}/hardware-health/temperature-limit",
        json={"limit_c": 90},
        headers=auth_headers,
    )
    assert missing.status_code == 404


def test_setting_a_temperature_limit_needs_the_role(client, auth_headers, session):
    host = _host(session, "laptop.lab")
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        response = client.put(
            f"/api/v1/host/{host.id}/hardware-health/temperature-limit",
            json={"limit_c": 90},
            headers=auth_headers,
        )
    assert response.status_code == 403
    session.expire_all()
    assert session.get(models.Host, host.id).hardware_temp_warning_c is None


def _flapping(session, fqdn, flips):
    """A host whose drive flapped ``flips`` times: one open event per flip."""
    host = _host(session, fqdn)
    for i in range(flips):
        hardware_health.apply_report(
            session, host, _report("warning" if i % 2 == 0 else "ok")
        )
        session.commit()
    return host


def _open_ids(client, auth_headers, host):
    return [
        e["id"]
        for e in client.get(
            "/api/v1/hardware-health/events",
            params={"open": "true", "host_id": str(host.id)},
            headers=auth_headers,
        ).json()["events"]
    ]


def test_bulk_resolve_the_picked_events(client, auth_headers, session):
    """Bryan, 2026-10-19: "managing the bajillion resolves is exhausting"."""
    host = _flapping(session, "nextcloud.lab", 4)
    ids = _open_ids(client, auth_headers, host)
    assert len(ids) == 4
    body = client.post(
        "/api/v1/hardware-health/events/resolve",
        json={"event_ids": ids[:3] + [str(uuid.uuid4()), "not-a-uuid"]},
        headers=auth_headers,
    ).json()
    assert body == {"resolved": 3, "skipped": 2, "remaining": 0}
    assert len(_open_ids(client, auth_headers, host)) == 1
    # one audit entry for the host, naming the events
    (audit,) = (
        session.query(models.AuditLog)
        .filter(models.AuditLog.entity_id == str(host.id))
        .filter(models.AuditLog.description.like("Hardware events resolved%"))
        .all()
    )
    details = (
        audit.details if isinstance(audit.details, dict) else json.loads(audit.details)
    )
    assert sorted(details["event_ids"]) == sorted(ids[:3])
    # resolving them again changes nothing
    again = client.post(
        "/api/v1/hardware-health/events/resolve",
        json={"event_ids": ids[:3]},
        headers=auth_headers,
    ).json()
    assert again["resolved"] == 0 and again["skipped"] == 3


def test_bulk_acknowledge_every_open_event_on_one_host(client, auth_headers, session):
    noisy = _flapping(session, "mail.lab", 3)
    other = _flapping(session, "beast.lab", 2)
    total = client.get(
        "/api/v1/hardware-health/events",
        params={"open": "true", "host_id": str(noisy.id)},
        headers=auth_headers,
    ).json()["total"]
    assert total == 3
    body = client.post(
        "/api/v1/hardware-health/events/acknowledge",
        json={"all_open": True, "host_id": str(noisy.id), "note": "lid closed"},
        headers=auth_headers,
    ).json()
    assert body == {"acknowledged": 3, "skipped": 0, "remaining": 0}
    events = hardware_health.host_view(session, noisy)["events"]
    assert all(e["acknowledged_at"] and not e["resolved_at"] for e in events)
    # the other host is untouched
    assert all(
        not e["acknowledged_at"]
        for e in hardware_health.host_view(session, other)["events"]
    )


def test_bulk_needs_the_role_and_one_selection(client, auth_headers, session):
    host = _flapping(session, "laptop.lab", 2)
    ids = _open_ids(client, auth_headers, host)
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        denied = client.post(
            "/api/v1/hardware-health/events/resolve",
            json={"event_ids": ids},
            headers=auth_headers,
        )
    assert denied.status_code == 403
    for body in ({}, {"event_ids": ids, "all_open": True}):
        bad = client.post(
            "/api/v1/hardware-health/events/resolve", json=body, headers=auth_headers
        )
        assert bad.status_code == 422
    too_many = client.post(
        "/api/v1/hardware-health/events/resolve",
        json={"event_ids": [str(uuid.uuid4()) for _ in range(1001)]},
        headers=auth_headers,
    )
    assert too_many.status_code == 422
    unknown_host = client.post(
        "/api/v1/hardware-health/events/resolve",
        json={"all_open": True, "host_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert unknown_host.status_code == 404
    assert len(_open_ids(client, auth_headers, host)) == 2


def test_a_vm_reads_no_physical_hardware_in_the_fleet(client, auth_headers, session):
    vm = _host(session, "droplet.lab")
    hardware_health.apply_report(
        session,
        vm,
        {"components": [], "sources": [{"name": "nvme", "status": "absent"}]},
    )
    vm.hardware_state = "unknown"  # stored by an older server: re-derived
    session.commit()
    body = client.get("/api/v1/hardware-health/hosts", headers=auth_headers).json()
    (row,) = [h for h in body["hosts"] if h["fqdn"] == "droplet.lab"]
    assert row["status"] == "none"
    assert body["hosts"][-1]["fqdn"] == "droplet.lab"  # least severe, last
    summary = client.get("/api/v1/hardware-health/summary", headers=auth_headers).json()
    assert summary["counts"].get("none") == 1 and "unknown" not in summary["counts"]
