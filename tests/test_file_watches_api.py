# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The file-watch endpoints, exercised THROUGH the router (Phase 21.1 S7).

Modelled on ``test_query_packs_api``, and for the same reason: S4 shipped with
seven read endpoints gated on a ``SecurityRoles`` member that did not exist,
and every GET returned 500 the first time a human opened the page. Service
tests were green throughout, because they never traverse a route.

So this suite asserts the wiring -- dependencies resolve, authorization names
REAL roles, route ordering holds, responses serialize -- and leaves the depth
to the service tests.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import file_watches
from backend.auth.auth_bearer import require_authenticated_user
from backend.persistence.partitions import get_tenant_db
from backend.security.roles import SecurityRoles
from backend.services import file_watch_service as fws


class FakeUser:
    userid = "admin@sysmanage.org"

    def __init__(self, roles=True):
        self._roles = roles

    def has_role(self, _role):
        return self._roles


class FakeQuery:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def order_by(self, *_a):
        return self

    def filter(self, *_a):
        return self

    def filter_by(self, **_kw):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def count(self):
        return len(self._rows)


class FakeDB:
    def __init__(self, rows=()):
        self._rows = rows

    def query(self, *_a):
        return FakeQuery(self._rows)


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(file_watches.router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = FakeUser
    app.dependency_overrides[get_tenant_db] = FakeDB
    # JWTBearer() and the license gate are instances built at import time, so
    # they are overridden by identity off the router rather than by calling
    # the factories again -- a fresh call makes a different object and the
    # override silently does not apply (which shows up as a 401).
    for dep in file_watches.router.dependencies:
        app.dependency_overrides[dep.dependency] = lambda: None
    # The catalog reads the SHARED partition through its own session.
    monkeypatch.setattr(fws, "list_shared_watches", lambda include_deprecated=False: [])
    return TestClient(app, raise_server_exceptions=False)


class TestReadEndpointsAreReachable:
    """The S4 regression, guarded here before it can happen again."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/file-watches",
            "/api/v1/file-watches/catalog",
            "/api/v1/file-watches/assignments/all",
        ],
    )
    def test_get_returns_two_hundred(self, client, path):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_host_state_returns_two_hundred(self, client):
        host = "11111111-1111-1111-1111-111111111111"
        response = client.get(f"/api/v1/file-watches/hosts/{host}/state")
        assert response.status_code == 200, response.text
        assert response.json()["paths"] == []


class TestEveryRoleNamedIsReal:
    """The exact S4 defect: a role constant that does not exist raises
    AttributeError inside the handler, which surfaces as a 500 rather than a
    403 and only on the first real request."""

    def test_all_referenced_roles_exist(self):
        source = (file_watches.__file__ or "").replace(".pyc", ".py")
        with open(source, "r", encoding="utf-8") as handle:
            text = handle.read()
        referenced = {
            line.split("SecurityRoles.")[1].split(")")[0].split(",")[0].strip()
            for line in text.splitlines()
            if "SecurityRoles." in line and "import" not in line
        }
        assert referenced
        for name in referenced:
            assert hasattr(SecurityRoles, name), f"SecurityRoles.{name} does not exist"


class TestRouteOrdering:
    """``/catalog`` must not be swallowed by ``/{watch_id}``.

    Both are one path segment, so declaration order in the module is the only
    thing keeping them apart -- a reordering turns the catalog into a lookup
    for a watch whose id is the literal string "catalog".
    """

    def test_catalog_is_not_parsed_as_a_watch_id(self, client):
        response = client.get("/api/v1/file-watches/catalog")
        assert response.status_code == 200
        assert response.json() == []

    def test_an_unparseable_watch_id_is_a_400_not_a_500(self, client):
        response = client.get("/api/v1/file-watches/not-a-uuid")
        assert response.status_code == 400, response.text


class TestWatchListValidation:
    """Refused at authoring time, not silently dropped at collection time.

    A path an operator believes is watched, and is not, produces a comparison
    that looks complete and is not -- the failure this slice exists to remove.
    """

    def _post(self, client, paths):
        return client.post("/api/v1/file-watches", json={"name": "w", "paths": paths})

    def test_an_empty_list_is_refused(self, client):
        assert self._post(client, []).status_code == 400

    def test_a_relative_path_is_refused(self, client):
        """It resolves against the agent's working directory, which differs
        between hosts -- so the same list would watch different files on
        each."""
        response = self._post(client, [{"path": "etc/hosts"}])
        assert response.status_code == 400
        assert "absolute" in response.text.lower()

    def test_a_duplicate_path_is_refused(self, client):
        response = self._post(client, [{"path": "/etc/hosts"}, {"path": "/etc/hosts"}])
        assert response.status_code == 400
        assert "duplicate" in response.text.lower()

    def test_too_many_paths_are_refused(self, client):
        paths = [
            {"path": f"/etc/f{i}"} for i in range(file_watches.MAX_PATHS_PER_WATCH + 1)
        ]
        assert self._post(client, paths).status_code == 400

    def test_a_windows_path_is_accepted_as_absolute(self, client):
        """A drive-letter path is absolute; refusing it would make the whole
        feature unusable on Windows."""
        problems = file_watches._validate_paths(
            [file_watches.PathIn(path="C:\\Windows\\System32\\drivers\\etc\\hosts")]
        )
        assert problems == []

    def test_a_unc_path_is_accepted(self, client):
        problems = file_watches._validate_paths(
            [file_watches.PathIn(path="\\\\server\\share\\config.ini")]
        )
        assert problems == []


class TestAssignmentValidation:
    def _post(self, client, body):
        return client.post("/api/v1/file-watches/assignments", json=body)

    def test_exactly_one_list_must_be_named(self, client):
        assert self._post(client, {"host_id": "x"}).status_code == 400
        assert (
            self._post(
                client,
                {"watch_id": "a", "shared_watch_id": "b", "host_id": "c"},
            ).status_code
            == 400
        )

    def test_exactly_one_target_must_be_named(self, client):
        watch = "11111111-1111-1111-1111-111111111111"
        assert self._post(client, {"watch_id": watch}).status_code == 400
        assert (
            self._post(
                client, {"watch_id": watch, "host_id": watch, "tag_id": watch}
            ).status_code
            == 400
        )

    def test_an_interval_below_the_floor_is_refused_with_a_reason(self, client):
        """Clamping silently would leave an operator believing they get
        minute-by-minute collection."""
        response = self._post(
            client,
            {
                "watch_id": "11111111-1111-1111-1111-111111111111",
                "host_id": "22222222-2222-2222-2222-222222222222",
                "interval_minutes": 1,
            },
        )
        assert response.status_code == 400
        assert str(file_watches.MIN_INTERVAL_MINUTES) in response.text


class TestAuthorisation:
    def test_a_user_without_the_role_is_refused(self, monkeypatch):
        app = FastAPI()
        app.include_router(file_watches.router, prefix="/api/v1")
        app.dependency_overrides[require_authenticated_user] = lambda: FakeUser(
            roles=False
        )  # pylint: disable=unnecessary-lambda
        app.dependency_overrides[get_tenant_db] = FakeDB
        for dep in file_watches.router.dependencies:
            app.dependency_overrides[dep.dependency] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/file-watches",
            json={"name": "w", "paths": [{"path": "/etc/hosts"}]},
        )
        assert response.status_code == 403, response.text
