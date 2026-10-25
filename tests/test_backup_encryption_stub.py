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


def test_a_licensed_server_mounts_no_backup_stub():
    client = _client({"backup_engine": True})
    answer = client.get("/api/v1/backup-encryption/host/x")
    assert answer.status_code == 404
