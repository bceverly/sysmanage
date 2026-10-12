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
    assert body == {"measured": None, "time_service": None, "history": []}


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
