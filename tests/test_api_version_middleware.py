"""
Tests for the API version middleware (Phase 13.2).

The middleware completes the ``/api/v1`` namespace: native ``/api/v1`` routes
pass through untouched, legacy unversioned routes become reachable under
``/api/v1`` too, the unversioned surface is never altered, and ``/api/v2`` is
unmapped.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.startup.api_version_middleware import ApiVersionMiddleware


def _client():
    app = FastAPI()

    # A native /api/v1 route (mirrors server_info et al.) ...
    @app.get("/api/v1/native")
    def native():
        return {"surface": "native-v1"}

    # ... and a legacy unversioned route (mirrors auth/login et al.).
    @app.get("/api/legacy")
    def legacy():
        return {"surface": "legacy"}

    app.add_middleware(ApiVersionMiddleware, fastapi_app=app)
    return TestClient(app)


class TestVersionedRouting:
    def test_native_v1_passthrough(self):
        # Must NOT be rewritten away — /api/native does not exist.
        resp = _client().get("/api/v1/native")
        assert resp.status_code == 200
        assert resp.json() == {"surface": "native-v1"}

    def test_legacy_unversioned_untouched(self):
        assert _client().get("/api/legacy").json() == {"surface": "legacy"}

    def test_legacy_reachable_under_v1(self):
        # /api/v1/legacy has no native route, so it rewrites to /api/legacy.
        resp = _client().get("/api/v1/legacy")
        assert resp.status_code == 200
        assert resp.json() == {"surface": "legacy"}

    def test_v2_not_mapped(self):
        assert _client().get("/api/v2/legacy").status_code == 404

    def test_unknown_v1_path_404(self):
        # No native route and no legacy fallback -> genuine 404.
        assert _client().get("/api/v1/does-not-exist").status_code == 404
