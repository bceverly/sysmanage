# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
CRUD + validation tests for the lifecycle-environment API (Phase 16, Slice 1).

Self-contained: builds a minimal app around ``content_lifecycle.router`` on an
in-memory SQLite shared DB, so we exercise the real router logic (create /
update / delete / reorder + the Library invariants) without the heavy api
conftest.  The 402 license gate is covered separately by
``test_content_lifecycle_gate.py``; here the engine is stubbed present.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

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

_ENV = "/api/v1/content-lifecycle/environments"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[models.SharedLifecycleEnvironment.__table__]
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

    # Engine present (gate passes) + auth bypassed for the CRUD surface.
    try:
        with patch.object(
            content_lifecycle.module_loader, "get_module", return_value=object()
        ), patch.object(JWTBearer, "__call__", _bypass_auth):
            with TestClient(app) as c:
                yield c
    finally:
        engine.dispose()


def _create(client, name, description=None):
    return client.post(_ENV, json={"name": name, "description": description})


class TestEnvironmentCrud:
    def test_first_environment_becomes_the_library(self, client):
        r = _create(client, "Library")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_library"] is True
        assert body["position"] == 0

    def test_subsequent_envs_append_and_are_not_library(self, client):
        _create(client, "Library")
        r = _create(client, "Dev")
        assert r.status_code == 200
        assert r.json()["is_library"] is False
        assert r.json()["position"] == 1
        r3 = _create(client, "Prod")
        assert r3.json()["position"] == 2

    def test_list_is_ordered_by_position(self, client):
        _create(client, "Library")
        _create(client, "Dev")
        _create(client, "Prod")
        names = [e["name"] for e in client.get(_ENV).json()]
        assert names == ["Library", "Dev", "Prod"]

    def test_duplicate_name_rejected(self, client):
        _create(client, "Dev")
        assert _create(client, "Dev").status_code == 409

    def test_empty_name_rejected(self, client):
        assert _create(client, "   ").status_code == 400

    def test_rename(self, client):
        _create(client, "Library")
        env_id = _create(client, "Staging").json()["id"]
        r = client.put(f"{_ENV}/{env_id}", json={"name": "Test"})
        assert r.status_code == 200
        assert r.json()["name"] == "Test"

    def test_rename_to_existing_name_rejected(self, client):
        _create(client, "Library")
        dev = _create(client, "Dev").json()["id"]
        _create(client, "Prod")
        assert client.put(f"{_ENV}/{dev}", json={"name": "Prod"}).status_code == 409

    def test_update_missing_env_404(self, client):
        r = client.put(
            f"{_ENV}/00000000-0000-0000-0000-000000000000", json={"name": "X"}
        )
        assert r.status_code == 404

    def test_delete_non_library(self, client):
        _create(client, "Library")
        dev = _create(client, "Dev").json()["id"]
        assert client.delete(f"{_ENV}/{dev}").status_code == 200
        assert [e["name"] for e in client.get(_ENV).json()] == ["Library"]

    def test_library_cannot_be_deleted(self, client):
        lib = _create(client, "Library").json()["id"]
        assert client.delete(f"{_ENV}/{lib}").status_code == 400


class TestEnvironmentReorder:
    def _seed(self, client):
        ids = {}
        for n in ("Library", "Dev", "Test", "Prod"):
            ids[n] = _create(client, n).json()["id"]
        return ids

    def test_reorder_reassigns_positions(self, client):
        ids = self._seed(client)
        order = [ids["Library"], ids["Test"], ids["Dev"], ids["Prod"]]
        r = client.post(f"{_ENV}/reorder", json={"ordered_ids": order})
        assert r.status_code == 200
        assert [e["name"] for e in r.json()] == ["Library", "Test", "Dev", "Prod"]
        assert [e["position"] for e in r.json()] == [0, 1, 2, 3]

    def test_reorder_requires_library_first(self, client):
        ids = self._seed(client)
        order = [ids["Dev"], ids["Library"], ids["Test"], ids["Prod"]]
        assert (
            client.post(f"{_ENV}/reorder", json={"ordered_ids": order}).status_code
            == 400
        )

    def test_reorder_requires_full_set(self, client):
        ids = self._seed(client)
        order = [ids["Library"], ids["Dev"]]  # missing Test/Prod
        assert (
            client.post(f"{_ENV}/reorder", json={"ordered_ids": order}).status_code
            == 400
        )
