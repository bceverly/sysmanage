"""
Tests for the rate-limit middleware (Phase 13.2).

Uses an ``X-Forwarded-For`` header so the client key is a real IP rather than
the exempt ``testclient`` host, letting the HTTP-level 429 path be exercised.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.startup.rate_limit_middleware import (
    RateLimitMiddleware,
    _client_key,
    _is_exempt,
)


def _app(**kwargs):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, **kwargs)

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/agent/status")
    def agent_status():
        return {"ok": True}

    return TestClient(app)


def _hdr(ip="9.9.9.9"):
    return {"X-Forwarded-For": ip}


class TestHelpers:
    def test_is_exempt(self):
        assert _is_exempt("/api/health") is True
        assert _is_exempt("/") is True
        assert _is_exempt("/api/agent/connect") is True
        assert _is_exempt("/api/v1/ping") is False

    def test_client_key_prefers_xff(self):
        scope = {
            "headers": [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
            "client": ("10.0.0.1", 1234),
        }
        assert _client_key(scope) == "1.2.3.4"

    def test_client_key_falls_back_to_socket(self):
        scope = {"headers": [], "client": ("10.0.0.1", 1234)}
        assert _client_key(scope) == "10.0.0.1"


class TestRateLimiting:
    def test_disabled_by_default_no_limit(self):
        client = _app(requests=1, window_seconds=60)  # enabled resolves to config=off
        for _ in range(5):
            assert client.get("/api/v1/ping", headers=_hdr()).status_code == 200

    def test_limit_enforced(self):
        client = _app(enabled=True, requests=2, window_seconds=60)
        assert client.get("/api/v1/ping", headers=_hdr()).status_code == 200
        assert client.get("/api/v1/ping", headers=_hdr()).status_code == 200
        resp = client.get("/api/v1/ping", headers=_hdr())
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_separate_clients_separate_buckets(self):
        client = _app(enabled=True, requests=1, window_seconds=60)
        assert client.get("/api/v1/ping", headers=_hdr("1.1.1.1")).status_code == 200
        # Different client gets its own allowance.
        assert client.get("/api/v1/ping", headers=_hdr("2.2.2.2")).status_code == 200
        # First client is now over its limit.
        assert client.get("/api/v1/ping", headers=_hdr("1.1.1.1")).status_code == 429

    def test_exempt_paths_never_limited(self):
        client = _app(enabled=True, requests=1, window_seconds=60)
        for _ in range(5):
            assert client.get("/api/health", headers=_hdr()).status_code == 200
            assert client.get("/api/agent/status", headers=_hdr()).status_code == 200

    def test_testclient_host_exempt(self):
        # No X-Forwarded-For -> client key is the TestClient host, which is exempt.
        client = _app(enabled=True, requests=1, window_seconds=60)
        for _ in range(5):
            assert client.get("/api/v1/ping").status_code == 200
