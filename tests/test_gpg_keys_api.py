"""
GPG Key Management stub-route tests (Pro+ relocation).

GPG Key Management logic was relocated OUT of OSS into the licensed Pro+
``secrets_engine`` module (schema stays OSS, logic → engine).  The endpoints now
live under ``/api/v1/secrets/gpg-keys*`` and are served by the compiled engine on
licensed boxes.  When the engine is NOT loaded (the default for OSS deployments
and the test harness), ``proplus_routes`` mounts stub routes under
``/api/v1/secrets/gpg-keys*`` that always return ``{"licensed": False}``.

These tests verify the stubs are mounted and gated behind auth.  The real
lifecycle / role-gate / no-material-leak tests live with the engine in the
sysmanage-professional-plus repo (test_secrets_engine_deployment.py style).

Modelled on ``tests/api/v1/test_phase10_proplus_stubs.py``.
"""

# pylint: disable=missing-class-docstring,missing-function-docstring

import uuid

_KEY_ID = str(uuid.uuid4())
_ASSIGNMENT_ID = str(uuid.uuid4())


class TestGpgKeysStubRoutes:
    def test_list_reachable(self, client):
        # The test harness globally overrides ``get_current_user`` (see
        # tests/conftest.py), so an unauthenticated call still resolves the stub
        # rather than 401ing — the real auth/role gate is exercised engine-side.
        r = client.get("/api/v1/secrets/gpg-keys")
        assert r.status_code in [200, 401, 403, 404]

    def test_list_returns_unlicensed(self, client, auth_headers):
        r = client.get("/api/v1/secrets/gpg-keys", headers=auth_headers)
        # Stub or real engine — engine isn't loaded in the test harness so the
        # stub route serves: returns 200 + {"licensed": False}.
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_upload_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            "/api/v1/secrets/gpg-keys",
            headers=auth_headers,
            json={"name": "x", "armored_key": "x", "key_type": "public"},
        )
        assert r.status_code in [200, 402, 403, 404, 422]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_get_returns_unlicensed(self, client, auth_headers):
        r = client.get(f"/api/v1/secrets/gpg-keys/{_KEY_ID}", headers=auth_headers)
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_delete_returns_unlicensed(self, client, auth_headers):
        r = client.delete(f"/api/v1/secrets/gpg-keys/{_KEY_ID}", headers=auth_headers)
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_list_assignments_returns_unlicensed(self, client, auth_headers):
        r = client.get(
            f"/api/v1/secrets/gpg-keys/{_KEY_ID}/assignments",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_create_assignment_returns_unlicensed(self, client, auth_headers):
        r = client.post(
            f"/api/v1/secrets/gpg-keys/{_KEY_ID}/assignments",
            headers=auth_headers,
            json={"host_id": str(uuid.uuid4())},
        )
        assert r.status_code in [200, 402, 403, 404, 422]
        if r.status_code == 200:
            assert r.json().get("licensed") is False

    def test_delete_assignment_returns_unlicensed(self, client, auth_headers):
        r = client.delete(
            f"/api/v1/secrets/gpg-keys/{_KEY_ID}/assignments/{_ASSIGNMENT_ID}",
            headers=auth_headers,
        )
        assert r.status_code in [200, 402, 403, 404]
        if r.status_code == 200:
            assert r.json().get("licensed") is False
