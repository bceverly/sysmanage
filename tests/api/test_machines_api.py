# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Machine endpoints (Phase 23.2 S2): a host's machine, held links, and the
admin's decision on one."""

import json
import uuid

from backend.persistence import models
from backend.services import machine_identity

UUID = "1a2b3c4d-5e6f-11b2-a85c-0f1e2d3c4b5a"


def _host(session, name):
    host = models.Host(
        id=uuid.uuid4(), fqdn=name, active=True, approval_status="approved"
    )
    session.add(host)
    session.commit()
    return host


def _report(session, host, vendor="LENOVO", serial="PF9ZQ7X1"):
    machine_identity.record_identity(
        session,
        host,
        {
            "system_uuid": UUID,
            "system_serial": serial,
            "vendor": vendor,
            "model": "x",
            "match_key": UUID,
            "status": {"system_uuid": "ran", "system_serial": "ran"},
        },
    )
    session.commit()


def test_a_host_shows_its_machine_and_the_other_oses_on_it(
    client, auth_headers, session
):
    windows, ubuntu = _host(session, "windows.t480"), _host(session, "ubuntu.t480")
    _report(session, windows)
    _report(session, ubuntu)
    response = client.get(f"/api/v1/host/{ubuntu.id}/machine", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["machine"]["system_serial"] == "PF9ZQ7X1"
    assert [h["fqdn"] for h in body["other_hosts"]] == ["windows.t480"]
    assert body["identity"]["status"]["system_uuid"] == "ran"
    assert body["conflict"] is None


def test_a_host_without_an_identity_says_why(client, auth_headers, session):
    host = _host(session, "unprivileged")
    host.hw_identity_status = json.dumps({"system_uuid": "unprivileged"})
    session.commit()
    body = client.get(f"/api/v1/host/{host.id}/machine", headers=auth_headers).json()
    assert body["machine"] is None
    assert body["identity"]["status"] == {"system_uuid": "unprivileged"}


def test_a_held_clone_is_listed_and_can_be_decided(client, auth_headers, session):
    original, clone = _host(session, "vm-a"), _host(session, "vm-b")
    _report(session, original, vendor="QEMU", serial=None)
    _report(session, clone, vendor="QEMU", serial=None)

    listed = client.get("/api/v1/machines/conflicts", headers=auth_headers).json()
    assert [c["host"]["fqdn"] for c in listed["conflicts"]] == ["vm-b"]
    assert listed["conflicts"][0]["reason"] == machine_identity.CONFLICT_VIRTUAL_CLONE

    response = client.post(
        f"/api/v1/host/{clone.id}/machine/resolve",
        json={"decision": "different"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert client.get("/api/v1/machines/conflicts", headers=auth_headers).json() == {
        "conflicts": []
    }


def test_deciding_without_a_conflict_or_with_a_bad_decision(
    client, auth_headers, session
):
    host = _host(session, "plain")
    nothing = client.post(
        f"/api/v1/host/{host.id}/machine/resolve",
        json={"decision": "same"},
        headers=auth_headers,
    )
    assert nothing.status_code == 409 and nothing.json()["detail"] == {
        "code": "no_conflict"
    }
    bad = client.post(
        f"/api/v1/host/{host.id}/machine/resolve",
        json={"decision": "maybe"},
        headers=auth_headers,
    )
    assert bad.status_code == 422


def test_an_unknown_host_is_404(client, auth_headers):
    response = client.get(f"/api/v1/host/{uuid.uuid4()}/machine", headers=auth_headers)
    assert response.status_code == 404


def test_the_endpoints_need_a_session(client):
    assert client.get(f"/api/v1/host/{uuid.uuid4()}/machine").status_code in (401, 403)
    assert client.get("/api/v1/machines/conflicts").status_code in (401, 403)
