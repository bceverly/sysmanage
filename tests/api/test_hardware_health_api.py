# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Hardware health endpoints (Phase 23.1 S2)."""

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
