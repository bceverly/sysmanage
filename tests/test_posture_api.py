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
