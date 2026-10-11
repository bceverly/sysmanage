# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Asset tag CSV import / export and held-tag endpoints (Phase 23.2 S5)."""

import uuid
from datetime import datetime

from backend.persistence import models
from backend.services import held_asset_tags

T480 = "6956e14c-347a-11b2-a85c-0f1e2d3c4b5a"


def _machine(session, tag=None):
    now = datetime.utcnow()
    machine = models.Machine(
        id=uuid.uuid4(),
        match_key=held_asset_tags.uuid_key(T480)[0],
        system_uuid=T480,
        system_serial="PF9ZQ7X1",
        asset_tag=tag,
        created_at=now,
        updated_at=now,
    )
    session.add(machine)
    session.commit()
    return machine


FILE = (
    "system_uuid,system_serial,asset_tag\n"
    f"{T480},,GDR-000001\n"
    ",NEW-1,GDR-000002\n"
)


def test_preview_writes_nothing(client, auth_headers, session):
    machine = _machine(session)
    body = client.post(
        "/api/v1/asset-tags/import/preview", json={"csv": FILE}, headers=auth_headers
    ).json()
    assert body["summary"] == {"assign": 1, "hold": 1}
    assert body["rows"][0]["machine_id"] == str(machine.id)
    session.refresh(machine)
    assert machine.asset_tag is None
    assert session.query(models.HeldAssetTag).count() == 0


def test_apply_writes_and_the_held_list_shows_the_hold(client, auth_headers, session):
    machine = _machine(session)
    body = client.post(
        "/api/v1/asset-tags/import/apply", json={"csv": FILE}, headers=auth_headers
    ).json()
    assert body["summary"] == {"assign": 1, "hold": 1}
    session.refresh(machine)
    assert machine.asset_tag == "GDR-000001"
    held = client.get("/api/v1/asset-tags/held", headers=auth_headers).json()["held"]
    assert [(h["kind"], h["identifier"], h["asset_tag"]) for h in held] == [
        ("system_serial", "NEW-1", "GDR-000002")
    ]


def test_an_unreadable_file_is_a_coded_422(client, auth_headers):
    response = client.post(
        "/api/v1/asset-tags/import/preview",
        json={"csv": "hostname\nx\n"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "missing_columns"}


def test_export_is_a_csv_download(client, auth_headers, session):
    _machine(session, tag="GDR-000001")
    response = client.get("/api/v1/asset-tags/export", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[1].startswith("GDR-000001,")


def test_releasing_a_hold(client, auth_headers):
    client.post(
        "/api/v1/asset-tags/import/apply", json={"csv": FILE}, headers=auth_headers
    )
    held = client.get("/api/v1/asset-tags/held", headers=auth_headers).json()["held"]
    gone = client.delete(
        f"/api/v1/asset-tags/held/{held[0]['id']}", headers=auth_headers
    )
    assert gone.status_code == 200
    left = client.get("/api/v1/asset-tags/held", headers=auth_headers).json()
    assert [h["id"] for h in left["held"]] == [h["id"] for h in held[1:]]
    again = client.delete(
        f"/api/v1/asset-tags/held/{held[0]['id']}", headers=auth_headers
    )
    assert again.status_code == 404
    bogus = client.delete("/api/v1/asset-tags/held/not-a-uuid", headers=auth_headers)
    assert bogus.status_code == 404
