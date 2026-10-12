# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Host clock and server clock endpoints (Phase 23.3 S2)."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.persistence import models


def _host(session, **fields):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn="t480.lab",
        active=True,
        approval_status="approved",
        **fields,
    )
    session.add(host)
    session.commit()
    return host


def test_an_unmeasured_host_says_so(client, auth_headers, session):
    host = _host(session)
    body = client.get(f"/api/v1/host/{host.id}/clock", headers=auth_headers).json()
    assert body["status"] == "unmeasured"
    assert body["bounds"]["source"] == "default"
    assert body["server"]["verified"] is True
    assert (body["measured"], body["time_service"], body["history"]) == (
        None,
        None,
        [],
    )
    assert body["service_ok"] is None


def test_measured_claimed_and_history(client, auth_headers, session):
    now = datetime.utcnow()
    host = _host(
        session,
        clock_offset_ms=1330.0,
        clock_rtt_ms=21.5,
        clock_samples=9,
        clock_method="exchange",
        clock_measured_at=now,
        time_service="w32time",
        time_service_running=False,
        time_status_at=now,
    )
    for days, offset in ((10, 9.0), (1, 1200.0)):
        session.add(
            models.HostClockSample(
                id=uuid.uuid4(),
                host_id=host.id,
                measured_at=now - timedelta(days=days),
                offset_ms=offset,
                method="exchange",
            )
        )
    session.commit()
    body = client.get(f"/api/v1/host/{host.id}/clock", headers=auth_headers).json()
    assert body["status"] == "warning"  # 1.33 s against the default 1 s / 5 s
    assert body["service_ok"] is False  # w32time is not running
    assert body["measured"]["offset_ms"] == 1330.0
    assert body["measured"]["samples"] == 9
    assert body["time_service"]["service"] == "w32time"
    assert body["time_service"]["running"] is False
    assert body["time_service"]["synchronized"] is None  # not reported
    assert [h["offset_ms"] for h in body["history"]] == [1200.0]  # 7 days only


def test_unknown_and_malformed_hosts_are_404(client, auth_headers):
    for host_id in (uuid.uuid4(), "nope"):
        response = client.get(f"/api/v1/host/{host_id}/clock", headers=auth_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == {"code": "host_not_found"}


def test_the_server_clock(client, auth_headers):
    status = {"reference": None, "offset_ms": None, "verified": False}
    with patch("backend.services.server_clock.status", return_value=status):
        body = client.get("/api/v1/time-sync/server", headers=auth_headers).json()
    assert body == status


def test_both_need_a_login(client):
    assert client.get("/api/v1/time-sync/server").status_code in (401, 403)


def test_the_fleet_is_worst_first(client, auth_headers, session):
    now = datetime.utcnow()
    for fqdn, offset in (("ok.lab", 3.0), ("bad.lab", -7200.0), ("warn.lab", 1500.0)):
        _host(session, clock_offset_ms=offset, clock_measured_at=now).fqdn = fqdn
    _host(session).fqdn = "new.lab"
    session.commit()
    body = client.get("/api/v1/time-sync/hosts", headers=auth_headers).json()
    assert [(h["fqdn"], h["status"]) for h in body["hosts"]] == [
        ("bad.lab", "critical"),
        ("warn.lab", "warning"),
        ("new.lab", "unmeasured"),
        ("ok.lab", "ok"),
    ]
    assert body["counts"] == {"critical": 1, "warning": 1, "unmeasured": 1, "ok": 1}


def _tag(session, name="domain-controllers"):
    now = datetime.utcnow()
    tag = models.Tag(id=uuid.uuid4(), name=name, created_at=now, updated_at=now)
    session.add(tag)
    session.commit()
    return tag


def test_overrides_are_set_listed_applied_and_cleared(client, auth_headers, session):
    now = datetime.utcnow()
    host = _host(session, clock_offset_ms=300.0, clock_measured_at=now)
    tag = _tag(session)
    session.add(
        models.HostTag(id=uuid.uuid4(), host_id=host.id, tag_id=tag.id, created_at=now)
    )
    session.commit()
    body = {
        "scope_kind": "tag",
        "scope_ref": str(tag.id),
        "warning_ms": 100,
        "critical_ms": 250,
    }
    response = client.put(
        "/api/v1/time-sync/bounds/override", json=body, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["overrides"][0]["critical_ms"] == 250.0
    clock = client.get(f"/api/v1/host/{host.id}/clock", headers=auth_headers).json()
    assert (clock["status"], clock["bounds"]["source"]) == ("critical", "tag")

    listed = client.get("/api/v1/time-sync/bounds", headers=auth_headers).json()
    assert listed["server"]["source"] == "default"
    assert [o["scope_kind"] for o in listed["overrides"]] == ["tag"]

    response = client.delete(
        "/api/v1/time-sync/bounds/override",
        params={"scope_kind": "tag", "scope_ref": str(tag.id)},
        headers=auth_headers,
    )
    assert response.json() == {"overrides": []}
    clock = client.get(f"/api/v1/host/{host.id}/clock", headers=auth_headers).json()
    assert clock["status"] == "ok"
    again = client.delete(
        "/api/v1/time-sync/bounds/override",
        params={"scope_kind": "tag", "scope_ref": str(tag.id)},
        headers=auth_headers,
    )
    assert again.status_code == 404


def test_bad_bounds_and_scopes_are_coded(client, auth_headers):
    cases = [
        (
            {"scope_kind": "tenant", "warning_ms": 5000, "critical_ms": 1000},
            422,
            "warning_not_below_critical",
        ),
        (
            {"scope_kind": "tenant", "warning_ms": 0, "critical_ms": 1000},
            422,
            "out_of_range",
        ),
        ({"scope_kind": "planet", "warning_ms": 1, "critical_ms": 2}, 422, "bad_scope"),
        (
            {
                "scope_kind": "tenant",
                "scope_ref": "x",
                "warning_ms": 1,
                "critical_ms": 2,
            },
            422,
            "bad_scope",
        ),
        (
            {"scope_kind": "site", "scope_ref": "x", "warning_ms": 1, "critical_ms": 2},
            422,
            "bad_scope",
        ),
        (
            {
                "scope_kind": "tag",
                "scope_ref": str(uuid.uuid4()),
                "warning_ms": 1,
                "critical_ms": 2,
            },
            404,
            "tag_not_found",
        ),
    ]
    for body, status, code in cases:
        response = client.put(
            "/api/v1/time-sync/bounds/override", json=body, headers=auth_headers
        )
        assert response.status_code == status, body
        assert response.json()["detail"] == {"code": code}


def test_server_bounds_are_saved_through_settings(client, auth_headers):
    stored = {}
    with patch(
        "backend.config.settings_service.set_setting",
        side_effect=lambda k, v: stored.update({k: v}) or True,
    ), patch(
        "backend.config.settings_service.get_setting",
        side_effect=lambda k, default=None: stored.get(k, default),
    ):
        response = client.put(
            "/api/v1/time-sync/bounds/server",
            json={"warning_ms": 500, "critical_ms": 2000},
            headers=auth_headers,
        )
    assert response.json()["source"] == "server"
    assert stored["time_sync_bounds"] == {"warning_ms": 500.0, "critical_ms": 2000.0}


def test_changing_bounds_needs_the_role(client, auth_headers, session):
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        response = client.put(
            "/api/v1/time-sync/bounds/server",
            json={"warning_ms": 500, "critical_ms": 2000},
            headers=auth_headers,
        )
    assert response.status_code == 403
    assert "Manage Time Sync" in response.json()["detail"]
