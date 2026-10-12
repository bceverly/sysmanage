# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Clock resync endpoints (Phase 23.3 S5)."""

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.persistence import models


def _host(session, offset=None, privileged=True):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
        is_agent_privileged=privileged,
        clock_offset_ms=offset,
        clock_measured_at=datetime.utcnow() if offset is not None else None,
    )
    session.add(host)
    session.commit()
    return host


@pytest.fixture
def queued():
    calls = []

    def fake(_db, host_id, command_type, parameters):
        calls.append(str(host_id))
        return str(uuid.uuid4())

    with patch("backend.services.config_mgmt_dispatch.queue_command", side_effect=fake):
        yield calls


def test_one_host_is_sent_at_once(client, auth_headers, session, queued):
    host = _host(session, offset=1330.0)
    body = client.post(
        f"/api/v1/host/{host.id}/clock/resync", headers=auth_headers
    ).json()
    assert body["status"] == "sent" and body["offset_before_ms"] == 1330.0
    assert queued == [str(host.id)]
    again = client.post(f"/api/v1/host/{host.id}/clock/resync", headers=auth_headers)
    assert again.status_code == 409
    assert again.json()["detail"] == {"code": "already_running"}
    listed = client.get(
        "/api/v1/time-sync/resyncs",
        params={"host_id": str(host.id)},
        headers=auth_headers,
    ).json()["resyncs"]
    assert [r["status"] for r in listed] == ["sent"]


def test_an_unknown_host_is_404(client, auth_headers):
    for host_id in (uuid.uuid4(), "nope"):
        response = client.post(
            f"/api/v1/host/{host_id}/clock/resync", headers=auth_headers
        )
        assert response.status_code == 404


def test_the_fleet_resync_takes_only_hosts_out_of_bounds(
    client, auth_headers, session, queued
):
    bad, warn, fine = (
        _host(session, 7200.0),
        _host(session, 1500.0),
        _host(session, 2.0),
    )
    unpriv = _host(session, 9000.0, privileged=False)
    body = client.post("/api/v1/time-sync/resync", json={}, headers=auth_headers).json()
    assert body["requested"] == 3
    assert body["counts"] == {"sent": 2, "unsupported": 1}
    assert sorted(queued) == sorted([str(bad.id), str(warn.id)])
    assert str(fine.id) not in queued and str(unpriv.id) not in queued
    batch = client.get(
        "/api/v1/time-sync/resyncs",
        params={"batch_id": body["batch_id"]},
        headers=auth_headers,
    ).json()["resyncs"]
    assert len(batch) == 3


def test_bad_statuses_and_ids_are_refused(client, auth_headers):
    for body, code in (
        ({"statuses": ["server_clock_off"]}, "bad_statuses"),
        ({"statuses": []}, "bad_statuses"),
        ({"host_ids": ["nope"]}, "bad_host_ids"),
    ):
        response = client.post(
            "/api/v1/time-sync/resync", json=body, headers=auth_headers
        )
        assert response.status_code == 422
        assert response.json()["detail"] == {"code": code}


def test_resync_needs_the_role(client, auth_headers, session):
    host = _host(session, 1.0)
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        response = client.post(
            f"/api/v1/host/{host.id}/clock/resync", headers=auth_headers
        )
    assert response.status_code == 403
    assert "Resync Host Clock" in response.json()["detail"]
