# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The threat-model and posture endpoints, through the router (21.4 S3).

Saving a model is a policy decision: administrators only. No model means
``threat_model: null`` and no items -- never an empty list that reads as
"nothing to do".
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import posture
from backend.auth.auth_bearer import require_authenticated_user
from backend.persistence.db import Base
from backend.persistence.partitions import get_tenant_db
from tests.services.test_posture_service import Engine

QUESTIONNAIRE = {"id": "sysmanage-threat-model", "version": 1, "questions": []}


class User:
    userid = "admin@sysmanage.org"
    is_admin = True


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(posture.router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = User

    def _db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_tenant_db] = _db
    app.state.factory = factory
    for dep in posture.router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    User.is_admin = True
    with patch.object(posture, "_engine", return_value=Engine()), patch.object(
        posture.threat_model_catalog, "load_questionnaire", return_value=QUESTIONNAIRE
    ), patch.object(
        posture.posture.threat_model_catalog,
        "load_questionnaire",
        return_value=QUESTIONNAIRE,
    ):
        yield TestClient(app, raise_server_exceptions=False)
    engine.dispose()


def test_no_model_means_no_list(client):
    assert client.get("/api/v1/advisor/posture").json() == {
        "threat_model": None,
        "items": [],
        "totals": {},
    }
    assert client.get("/api/v1/advisor/threat-model").json() == {
        "current": None,
        "versions": [],
    }


def test_an_admin_saves_versions_and_sees_the_changes(client):
    first = client.post("/api/v1/advisor/threat-model", json={"answers": {"q": "no"}})
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/advisor/threat-model", json={"answers": {"q": "yes"}})
    assert second.json()["threat_model"]["model_version"] == 2
    assert second.json()["changes"] == {"attributes_on": ["x"]}
    models_out = client.get("/api/v1/advisor/threat-model").json()
    assert models_out["current"]["model_version"] == 2
    assert [v["model_version"] for v in models_out["versions"]] == [2, 1]
    assert (
        client.get("/api/v1/advisor/posture").json()["threat_model"]["model_version"]
        == 2
    )


def test_only_an_administrator_may_change_the_model(client):
    User.is_admin = False
    response = client.post(
        "/api/v1/advisor/threat-model", json={"answers": {"q": "yes"}}
    )
    assert response.status_code == 403


def test_the_questionnaire_is_served_and_a_missing_catalog_is_a_503(client):
    assert (
        client.get("/api/v1/advisor/threat-model/questionnaire").json() == QUESTIONNAIRE
    )
    with patch.object(
        posture.threat_model_catalog, "load_questionnaire", return_value=None
    ):
        assert (
            client.get("/api/v1/advisor/threat-model/questionnaire").status_code == 503
        )


def _open_item(factory_client):
    """Save a model and an OPEN item directly (the evaluation is service-tested)."""
    client, factory = factory_client
    client.post("/api/v1/advisor/threat-model", json={"answers": {"q": "yes"}})
    from backend.persistence import models  # noqa: PLC0415

    with factory() as db:
        db.add(
            models.PostureItem(
                scope_kind="tenant",
                scope_ref="",
                rule_source="tenant",
                rule_key="PM-X",
                rule_version=1,
                state="open",
                outcome="fires",
                managed_by="tenant",
                risk=12,
            )
        )
        db.commit()


@pytest.fixture
def factory_client(client):
    return client, client.app.state.factory


def test_waiving_overlays_the_item_and_counts_it_as_waived(factory_client):
    client, _ = factory_client
    _open_item(factory_client)
    with patch.object(
        posture.posture,
        "rule_definition",
        return_value={"applies_when": {"always": True}},
    ):
        response = client.post(
            "/api/v1/advisor/posture/PM-X/waiver", json={"reason": "accepted"}
        )
    assert response.status_code == 200, response.text
    listing = client.get("/api/v1/advisor/posture").json()
    assert listing["totals"] == {"waived": 1}
    item = listing["items"][0]
    assert (item["state"], item["evaluated_state"]) == ("waived", "open")
    assert item["waiver"]["reason"] == "accepted"
    again = client.post("/api/v1/advisor/posture/PM-X/waiver", json={"reason": "x"})
    assert (again.status_code, again.json()["detail"]) == (
        409,
        {"code": "already_waived"},
    )
    removed = client.delete("/api/v1/advisor/posture/PM-X/waiver")
    assert removed.status_code == 200
    assert client.get("/api/v1/advisor/posture").json()["totals"] == {"open": 1}


def test_waivers_need_an_administrator_and_a_known_item(factory_client):
    client, _ = factory_client
    _open_item(factory_client)
    assert (
        client.post(
            "/api/v1/advisor/posture/NOPE/waiver", json={"reason": "r"}
        ).status_code
        == 404
    )
    User.is_admin = False
    assert (
        client.post(
            "/api/v1/advisor/posture/PM-X/waiver", json={"reason": "r"}
        ).status_code
        == 403
    )


def test_reaffirm_needs_no_body(factory_client):
    """Found live: an optional reason still made FastAPI demand a body (422)."""
    client, _ = factory_client
    _open_item(factory_client)
    response = client.post("/api/v1/advisor/posture/PM-X/waiver/reaffirm")
    assert (response.status_code, response.json()["detail"]) == (
        409,
        {"code": "not_waived"},
    )


def test_the_list_says_how_each_item_is_fixed(factory_client):
    client, _ = factory_client
    _open_item(factory_client)
    with patch.object(
        posture.posture,
        "rules_by_key",
        return_value={"PM-X": {"remedy": "configure_alerting"}},
    ):
        item = client.get("/api/v1/advisor/posture").json()["items"][0]
    assert (item["remedy"], item["remedy_kind"], item["remedy_target"]) == (
        "configure_alerting",
        "guided",
        "alerting",
    )


def test_applying_a_fleet_remedy_needs_the_per_host_role(factory_client):
    client, _ = factory_client
    _open_item(factory_client)
    User.has_role = lambda self, role: False
    with patch.object(
        posture.posture, "rule_definition", return_value={"remedy": "enable_firewall"}
    ):
        response = client.post("/api/v1/advisor/posture/PM-X/remedy")
    del User.has_role
    assert response.status_code == 403


def test_an_unavailable_remedy_is_a_409_code(factory_client):
    client, _ = factory_client
    _open_item(factory_client)
    with patch.object(
        posture.posture,
        "rule_definition",
        return_value={"remedy": "configure_alerting"},
    ):
        response = client.post("/api/v1/advisor/posture/PM-X/remedy")
        preview = client.get("/api/v1/advisor/posture/PM-X/remedy").json()
    assert (response.status_code, response.json()["detail"]) == (
        409,
        {"code": "not_automated"},
    )
    assert preview["kind"] == "guided"


def test_history_and_the_regressed_flag_come_through_the_api(factory_client):
    client, factory = factory_client
    _open_item(factory_client)
    from datetime import datetime  # noqa: PLC0415

    from backend.persistence import models  # noqa: PLC0415

    with factory() as db:
        db.add(
            models.PostureItemEvent(
                scope_kind="tenant",
                scope_ref="",
                rule_key="PM-X",
                from_state="satisfied",
                to_state="open",
                cause="evaluation",
                at=datetime(2026, 9, 27),
            )
        )
        db.commit()
    assert (
        client.get("/api/v1/advisor/posture/history").json()["events"][0]["kind"]
        == "regression"
    )
    assert (
        client.get("/api/v1/advisor/posture/PM-X/history").json()["events"][0][
            "rule_key"
        ]
        == "PM-X"
    )
    assert client.get("/api/v1/advisor/posture").json()["items"][0]["regressed"] is True
    assert (
        client.get(
            "/api/v1/advisor/threat-model/diff?from_version=1&to_version=7"
        ).status_code
        == 404
    )
