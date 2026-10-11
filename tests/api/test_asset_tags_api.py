# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Asset-tag scheme and machine-tag endpoints (Phase 23.2 S3)."""

import uuid
from datetime import datetime

from backend.persistence import models

GDR = {"mode": "builder", "prefix": "GDR", "separator": "-", "digits": 6}


def _machine(session, tag=None):
    now = datetime.utcnow()
    machine = models.Machine(
        id=uuid.uuid4(),
        match_key=str(uuid.uuid4()),
        asset_tag=tag,
        created_at=now,
        updated_at=now,
    )
    session.add(machine)
    session.commit()
    return machine


def test_the_unsaved_scheme_enforces_nothing(client, auth_headers):
    body = client.get("/api/v1/asset-tags/scheme", headers=auth_headers).json()
    assert body["scheme"]["enforce"] is False
    assert body["nonconforming"] == []


def test_a_draft_previews_without_saving(client, auth_headers, session):
    _machine(session, "GDR-000041")
    _machine(session, "legacy-7")
    body = client.post(
        "/api/v1/asset-tags/scheme/preview", json=GDR, headers=auth_headers
    ).json()
    assert body["preview"] == "GDR-000042"
    assert body["next_free"] == "GDR-000042"
    assert body["nonconforming"] == ["legacy-7"]
    saved = client.get("/api/v1/asset-tags/scheme", headers=auth_headers).json()
    assert saved["scheme"]["prefix"] == ""


def test_saving_reports_nonconforming_tags_and_never_rewrites(
    client, auth_headers, session
):
    legacy = _machine(session, "legacy-7")
    response = client.put(
        "/api/v1/asset-tags/scheme", json={**GDR, "enforce": True}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["nonconforming"] == ["legacy-7"]
    session.refresh(legacy)
    assert legacy.asset_tag == "legacy-7"


def test_an_invalid_scheme_names_its_fields(client, auth_headers):
    response = client.put(
        "/api/v1/asset-tags/scheme",
        json={**GDR, "digits": 0, "separator": "|"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "invalid_scheme",
        "fields": ["separator", "digits"],
    }


def test_setting_a_tag_checks_the_scheme_and_uniqueness(client, auth_headers, session):
    client.put(
        "/api/v1/asset-tags/scheme", json={**GDR, "enforce": True}, headers=auth_headers
    )
    first, second = _machine(session), _machine(session)

    def put(machine, tag):
        return client.put(
            f"/api/v1/machine/{machine.id}/asset-tag",
            json={"asset_tag": tag},
            headers=auth_headers,
        )

    assert put(first, "GDR-000001").status_code == 200
    bad = put(second, "GDR-1")
    assert (
        bad.status_code == 422
        and bad.json()["detail"]["code"] == "does_not_match_scheme"
    )
    taken = put(second, "gdr-000001".upper())
    assert taken.status_code == 422 and taken.json()["detail"]["code"] == "duplicate"
    assert put(first, "GDR-000001").status_code == 200  # re-saving its own tag
    assert put(first, None).json()["asset_tag"] is None  # clearing


def test_the_entry_time_check(client, auth_headers, session):
    machine = _machine(session, "ANY-1")
    ok = client.get(
        "/api/v1/asset-tags/check", params={"tag": "ANY-2"}, headers=auth_headers
    ).json()
    assert ok == {"ok": True, "reason": None}
    dup = client.get(
        "/api/v1/asset-tags/check", params={"tag": "any-1"}, headers=auth_headers
    ).json()
    assert dup == {"ok": False, "reason": "duplicate"}
    own = client.get(
        "/api/v1/asset-tags/check",
        params={"tag": "ANY-1", "machine_id": str(machine.id)},
        headers=auth_headers,
    ).json()
    assert own["ok"] is True


def test_an_unknown_machine_is_404(client, auth_headers):
    response = client.put(
        f"/api/v1/machine/{uuid.uuid4()}/asset-tag",
        json={"asset_tag": "X-1"},
        headers=auth_headers,
    )
    assert response.status_code == 404
