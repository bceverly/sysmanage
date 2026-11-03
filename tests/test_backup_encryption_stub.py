# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Without backup_engine, encrypted backups answer 402 (never 200 or 404)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import proplus_routes_stubs as stubs
from backend.auth.auth_bearer import get_current_user


def _client(results):
    app = FastAPI()
    stubs._mount_backup_stubs(app, results)  # pylint: disable=protected-access
    app.dependency_overrides[get_current_user] = lambda: "admin@example.com"
    return TestClient(app)


def test_unlicensed_backup_encryption_is_402():
    client = _client({})
    for method in (client.get, client.post):
        answer = method(
            "/api/v1/backup-encryption/host/00000000-0000-0000-0000-000000000001"
        )
        assert answer.status_code == 402
        assert "backup engine" in answer.json()["detail"]


def test_every_engine_route_is_402_unlicensed():
    """Each route backup_engine mounts under /v1/backup-encryption has a 402
    stub, not only the host ones (edition audit, 2026-11-03)."""
    client = _client({})
    host = "/api/v1/backup-encryption/host/00000000-0000-0000-0000-000000000001"
    for method, path in (
        ("post", host + "/rotate"),
        ("get", "/api/v1/backup-encryption/settings"),
        ("put", "/api/v1/backup-encryption/settings"),
        ("get", "/api/v1/backup-encryption/signing"),
        ("post", "/api/v1/backup-encryption/signing"),
        ("post", "/api/v1/backup-encryption/break-glass"),
    ):
        answer = getattr(client, method)(path)
        assert answer.status_code == 402, (method, path, answer.status_code)


def test_the_stubs_cover_every_engine_route():
    """A new engine route without a stub fails here: the stub list is read
    against the engine's own source."""
    import pathlib  # pylint: disable=import-outside-toplevel
    import re  # pylint: disable=import-outside-toplevel

    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "sysmanage-professional-plus/module-source/backup_engine/backup_engine.pyx"
    )
    if not source.exists():
        return  # the engine's source is not beside this checkout (CI)
    routes = set(
        re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"\)', source.read_text())
    )
    client = _client({})
    for method, path in routes:
        url = "/api/v1/backup-encryption" + path.replace("{host_id}", "x")
        answer = getattr(client, method)(url)
        assert answer.status_code == 402, (method, path, answer.status_code)


def test_a_licensed_server_mounts_no_backup_stub():
    client = _client({"backup_engine": True})
    answer = client.get("/api/v1/backup-encryption/host/x")
    assert answer.status_code == 404
