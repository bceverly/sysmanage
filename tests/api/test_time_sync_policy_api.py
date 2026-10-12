# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet NTP policy endpoints (Phase 23.3 S5b)."""

import json
import uuid
from unittest.mock import patch

import pytest

from backend.persistence import models
from tests.services import _fake_ntp_engine


@pytest.fixture
def licensed():
    with patch("backend.licensing.feature_gate._check_module_licensed_http"), patch(
        "backend.licensing.feature_gate._check_module_loaded_http"
    ), patch(
        "backend.services.config_mgmt_spec_shim.engine_module",
        return_value=_fake_ntp_engine,
    ):
        yield


def _host(session, servers):
    host = models.Host(
        id=uuid.uuid4(),
        fqdn=f"{uuid.uuid4().hex[:6]}.lab",
        active=True,
        approval_status="approved",
        platform="Linux",
        time_service="chrony",
        time_configured_servers=json.dumps(servers),
        time_service_enabled=True,
    )
    session.add(host)
    session.commit()
    return host


def test_set_list_and_judge(client, auth_headers, session, licensed):
    good, bad = _host(session, ["ntp1.lab"]), _host(session, ["pool.ntp.org"])
    body = {"scope_kind": "fleet", "servers": ["ntp1.lab"], "enforce": True}
    saved = client.put(
        "/api/v1/time-sync/ntp-policies", json=body, headers=auth_headers
    )
    assert saved.status_code == 200 and saved.json()["enforce"] is True
    listed = client.get("/api/v1/time-sync/ntp-policies", headers=auth_headers).json()
    assert [p["servers"] for p in listed["policies"]] == [["ntp1.lab"]]
    rows = {
        r["fqdn"]: r
        for r in client.get(
            "/api/v1/time-sync/ntp-compliance", headers=auth_headers
        ).json()["hosts"]
    }
    assert rows[good.fqdn]["compliant"] is True
    assert rows[bad.fqdn]["findings"][0]["code"] == "servers_differ"
    fleet = client.get("/api/v1/time-sync/hosts", headers=auth_headers).json()["hosts"]
    by = {h["fqdn"]: h for h in fleet}
    assert by[bad.fqdn]["policy_findings"] == ["servers_differ"]
    clock = client.get(f"/api/v1/host/{bad.id}/clock", headers=auth_headers).json()
    assert clock["ntp_policy"]["compliant"] is False
    assert clock["ntp_policy"]["configured_servers"] == ["pool.ntp.org"]


def test_bad_policies_are_coded(client, auth_headers, licensed):
    for body, status, code in (
        ({"scope_kind": "fleet", "servers": []}, 422, "no_servers"),
        ({"scope_kind": "fleet", "servers": ["a b"]}, 422, "bad_server"),
        ({"scope_kind": "planet", "servers": ["a"]}, 422, "bad_scope"),
        ({"scope_kind": "fleet", "scope_ref": "x", "servers": ["a"]}, 422, "bad_scope"),
        (
            {"scope_kind": "tag", "scope_ref": str(uuid.uuid4()), "servers": ["a"]},
            404,
            "tag_not_found",
        ),
    ):
        response = client.put(
            "/api/v1/time-sync/ntp-policies", json=body, headers=auth_headers
        )
        assert response.status_code == status, body
        assert response.json()["detail"] == {"code": code}


def test_remove_falls_back(client, auth_headers, licensed):
    client.put(
        "/api/v1/time-sync/ntp-policies",
        json={"scope_kind": "fleet", "servers": ["a.lab"]},
        headers=auth_headers,
    )
    gone = client.delete(
        "/api/v1/time-sync/ntp-policies",
        params={"scope_kind": "fleet"},
        headers=auth_headers,
    )
    assert gone.json() == {"removed": True}
    again = client.delete(
        "/api/v1/time-sync/ntp-policies",
        params={"scope_kind": "fleet"},
        headers=auth_headers,
    )
    assert again.status_code == 404


def test_without_the_engine_the_clock_endpoint_says_nothing(
    client, auth_headers, session
):
    host = _host(session, ["a.lab"])
    with patch(
        "backend.services.config_mgmt_spec_shim.engine_module", return_value=None
    ):
        clock = client.get(f"/api/v1/host/{host.id}/clock", headers=auth_headers).json()
        fleet = client.get("/api/v1/time-sync/hosts", headers=auth_headers).json()
    assert clock["ntp_policy"] is None
    assert fleet["hosts"][0]["policy_compliant"] is None


def test_the_policy_api_is_gated(client, auth_headers):
    from fastapi import HTTPException  # noqa: PLC0415

    def refuse(_module):
        raise HTTPException(status_code=403, detail={"error": "module_not_licensed"})

    with patch(
        "backend.licensing.feature_gate._check_module_licensed_http", side_effect=refuse
    ):
        response = client.get("/api/v1/time-sync/ntp-policies", headers=auth_headers)
    assert response.status_code == 403


def test_policy_changes_need_the_role(client, auth_headers, licensed):
    with patch(
        "backend.persistence.models.User.has_role", return_value=False, create=True
    ):
        response = client.put(
            "/api/v1/time-sync/ntp-policies",
            json={"scope_kind": "fleet", "servers": ["a.lab"]},
            headers=auth_headers,
        )
    assert response.status_code == 403
