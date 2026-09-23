# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The query-pack endpoints, exercised THROUGH the router (Phase 21.1 S4).

WHY THIS FILE EXISTS
--------------------
S4 shipped with seven read endpoints gated on ``SecurityRoles.VIEW_SCRIPT``,
which does not exist. Every GET returned 500 the first time a human opened the
page. The service-layer tests were green throughout, because they call the
service directly and never traverse a route.

So this suite asserts the thing those could not: that a request actually
reaches a handler and comes back 2xx. The assertions are deliberately shallow
-- status codes and shape -- because the depth is already covered elsewhere.
What matters here is the wiring: dependencies resolve, authorisation names
real roles, and response models serialise.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import query_packs
from backend.auth.auth_bearer import require_authenticated_user
from backend.persistence.partitions import get_tenant_db
from backend.services import query_pack_service as svc


class FakeUser:
    userid = "admin@sysmanage.org"

    def has_role(self, _role):
        return True


class FakeQuery:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def order_by(self, *_a):
        return self

    def filter(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    def __init__(self, rows=()):
        self._rows = rows

    def query(self, *_a):
        return FakeQuery(self._rows)


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(query_packs.router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = FakeUser
    app.dependency_overrides[get_tenant_db] = FakeDB
    # JWTBearer() and the licence gate are instances built at import time, so
    # they are overridden by identity off the router rather than by calling
    # the factories again — a fresh call makes a different object and the
    # override silently does not apply (which shows up as a 401).
    for dep in query_packs.router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    # The catalog reads the SHARED partition through its own session.
    monkeypatch.setattr(svc, "list_shared_packs", lambda include_deprecated=False: [])
    return TestClient(app, raise_server_exceptions=False)


class TestReadEndpointsAreReachable:
    """The regression. Each of these returned 500 on a role that never existed."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/query-packs/catalog",
            "/api/v1/query-packs",
            "/api/v1/query-packs/runs/recent",
            "/api/v1/query-packs/assignments/all",
        ],
    )
    def test_get_returns_two_hundred(self, client, path):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)


class TestRouteOrdering:
    """``/catalog`` must not be swallowed by ``/{pack_id}``.

    Both are one path segment, so the declaration order in the module is the
    only thing keeping them apart — and a reordering would turn the catalog
    into a lookup for a pack whose id is the literal string "catalog".
    """

    def test_catalog_is_not_parsed_as_a_pack_id(self, client):
        response = client.get("/api/v1/query-packs/catalog")
        assert response.status_code == 200
        assert response.json() == []

    def test_an_unparseable_pack_id_is_a_400_not_a_500(self, client):
        response = client.get("/api/v1/query-packs/not-a-uuid")
        assert response.status_code == 400, response.text


class TestValidationEndpoint:
    def test_problems_come_back_without_storing_anything(self, client, monkeypatch):
        monkeypatch.setattr(
            query_packs.shim,
            "validate_pack",
            lambda _pack: {"valid": False, "problems": ["a query may only read"]},
        )
        response = client.post(
            "/api/v1/query-packs/validate",
            json={"name": "p", "queries": [{"name": "q", "sql": "DELETE FROM users"}]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["valid"] is False
        assert body["problems"] == ["a query may only read"]


class TestMutationsStillCarryARole:
    """Reads are gated by the router's JWT + licence dependencies; mutations
    additionally require a role. Removing the bogus VIEW_SCRIPT check must not
    have removed the real ones."""

    def test_create_is_refused_without_the_role(self, client):
        class NoRoleUser(FakeUser):
            def has_role(self, _role):
                return False

        client.app.dependency_overrides[require_authenticated_user] = NoRoleUser
        response = client.post(
            "/api/v1/query-packs",
            json={"name": "p", "queries": [{"name": "q", "sql": "SELECT 1"}]},
        )
        assert response.status_code == 403, response.text
