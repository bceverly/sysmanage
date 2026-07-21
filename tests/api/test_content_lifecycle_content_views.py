# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
CRUD + validation tests for the content-view API (Phase 16, Slice 2).

Self-contained: builds a minimal app around ``content_lifecycle.router`` on an
in-memory SQLite shared DB, exercising the real router logic (create / detail /
update / delete + membership replacement + retention clamping) without the heavy
api conftest.  The 402 license gate is covered by ``test_content_lifecycle_gate``;
here the engine is stubbed present.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import content_lifecycle
from backend.auth.auth_bearer import JWTBearer
from backend.persistence import models
from backend.persistence.db import Base
from backend.persistence.partitions import get_shared_db

_CV = "/api/v1/content-lifecycle/content-views"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            models.SharedContentView.__table__,
            models.SharedContentViewRepo.__table__,
            models.SharedContentViewFilter.__table__,
            models.SharedContentViewVersion.__table__,
        ],
    )
    session_local = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(content_lifecycle.router, prefix="/api/v1")

    def _shared_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_shared_db] = _shared_db

    async def _bypass_auth(self, request: Request):
        return "test-user"

    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=object()
        ), patch.object(JWTBearer, "__call__", _bypass_auth):
            with TestClient(app) as c:
                yield c
    finally:
        engine.dispose()


def _mid():
    return str(uuid.uuid4())


def _create(client, name, **kw):
    return client.post(_CV, json={"name": name, **kw})


class TestContentViewCrud:
    def test_create_minimal(self, client):
        r = _create(client, "RHEL9 Base")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "RHEL9 Base"
        assert body["composite"] is False
        assert body["keep_versions"] == 5
        assert body["repos"] == []
        assert body["versions"] == []

    def test_create_with_members(self, client):
        m1, m2 = _mid(), _mid()
        r = _create(
            client,
            "App Stack",
            repos=[{"mirror_id": m1}, {"mirror_id": m2, "position": 5}],
        )
        assert r.status_code == 200, r.text
        repos = r.json()["repos"]
        assert {x["mirror_id"] for x in repos} == {m1, m2}

    def test_duplicate_name_rejected(self, client):
        _create(client, "Dup")
        assert _create(client, "Dup").status_code == 409

    def test_blank_name_rejected(self, client):
        assert _create(client, "   ").status_code == 400

    def test_member_without_ref_rejected(self, client):
        r = _create(client, "Bad", repos=[{"position": 1}])
        assert r.status_code == 400

    def test_keep_versions_clamped(self, client):
        assert _create(client, "Hi", keep_versions=999).json()["keep_versions"] == 10
        assert _create(client, "Lo", keep_versions=0).json()["keep_versions"] == 1

    def test_get_detail_404(self, client):
        assert client.get(f"{_CV}/{_mid()}").status_code == 404

    def test_get_detail(self, client):
        cv_id = _create(client, "Detail", repos=[{"mirror_id": _mid()}]).json()["id"]
        got = client.get(f"{_CV}/{cv_id}")
        assert got.status_code == 200
        assert len(got.json()["repos"]) == 1

    def test_update_rename_and_keep(self, client):
        cv_id = _create(client, "Orig").json()["id"]
        r = client.put(f"{_CV}/{cv_id}", json={"name": "Renamed", "keep_versions": 3})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"
        assert r.json()["keep_versions"] == 3

    def test_update_rename_clash_rejected(self, client):
        _create(client, "Taken")
        cv_id = _create(client, "Mine").json()["id"]
        assert client.put(f"{_CV}/{cv_id}", json={"name": "Taken"}).status_code == 409

    def test_update_replaces_membership(self, client):
        cv_id = _create(client, "Repl", repos=[{"mirror_id": _mid()}]).json()["id"]
        new_mirror = _mid()
        r = client.put(f"{_CV}/{cv_id}", json={"repos": [{"mirror_id": new_mirror}]})
        assert r.status_code == 200
        repos = r.json()["repos"]
        assert len(repos) == 1 and repos[0]["mirror_id"] == new_mirror

    def test_delete(self, client):
        cv_id = _create(client, "Gone").json()["id"]
        deleted = client.delete(f"{_CV}/{cv_id}")
        assert deleted.status_code == 200
        assert client.get(f"{_CV}/{cv_id}").status_code == 404

    def test_list_summary_shape(self, client):
        _create(client, "Alpha", repos=[{"mirror_id": _mid()}])
        rows = client.get(_CV).json()
        assert rows[0]["name"] == "Alpha"
        assert rows[0]["repo_count"] == 1
        assert rows[0]["version_count"] == 0
        assert rows[0]["latest_published_version"] is None
