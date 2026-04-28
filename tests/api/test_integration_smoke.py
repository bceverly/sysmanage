"""
End-to-end smoke tests for the running FastAPI app.

These exist to populate @pytest.mark.integration so the
.github/workflows/integration-tests.yml `integration-server` job has
something real to do.  They are deliberately focused on cross-cutting
flows (router → middleware → DB) rather than unit-testing individual
functions, so they catch wiring regressions that single-layer tests
in tests/api/ would miss.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring,invalid-name

import pytest


@pytest.mark.integration
def test_health_endpoint_returns_healthy(client):
    """The unauthenticated /api/health endpoint must respond 200 + status=healthy.

    This is the same endpoint the load harness in tests/load/run.py polls
    and the contract is documented in backend/benchmarks/test_response_times.py.
    Any change that breaks the response shape here breaks the load test.
    """
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "healthy"}, f"unexpected health body: {body!r}"


@pytest.mark.integration
def test_health_endpoint_supports_head(client):
    """HEAD on /api/health must work too — used by some monitors / load balancers."""
    resp = client.head("/api/health")
    assert resp.status_code == 200


@pytest.mark.integration
def test_root_endpoint_responds(client):
    """The root / endpoint exists; we don't pin its exact body."""
    resp = client.get("/")
    assert resp.status_code == 200
    # Body shape is { "message": "Hello World" } today; that's a UI placeholder
    # not a contract, so just assert it deserialises to something dict-shaped.
    assert isinstance(resp.json(), dict)


@pytest.mark.integration
def test_unknown_endpoint_returns_404(client):
    """A nonsense path must hit FastAPI's default 404, not crash the app."""
    resp = client.get("/this-route-does-not-exist-zzz123")
    assert resp.status_code == 404


@pytest.mark.integration
def test_openapi_schema_is_served(client):
    """FastAPI's /openapi.json should be available — a basic stack-up smoke check."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "openapi" in schema
    assert "paths" in schema
    # Sanity: at least the health endpoint should be in the schema
    assert "/api/health" in schema["paths"]
