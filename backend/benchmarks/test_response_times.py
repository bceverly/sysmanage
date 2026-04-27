"""
Phase 6 response-time micro-benchmark.

Measures p50/p95 in-process latency for hot endpoints using FastAPI's
TestClient.  This is NOT a load test — it characterises the application
itself with the network and DB pool factored out.  Use the WebSocket
scalability harness (still TBD) for end-to-end agent-fleet load.

Usage:
    pytest backend/benchmarks/test_response_times.py -v -s
        --benchmark-min-rounds=200

Baseline expectations (committed 2026-04-26, recorded against a fresh
test DB on a workstation-class machine — your numbers will differ):

    GET /api/health                p50 < 5ms    p95 < 20ms
    GET /api/v1/automation/scripts p50 < 25ms   p95 < 80ms   (empty list)
    GET /api/v1/fleet/groups       p50 < 25ms   p95 < 80ms   (empty list)

If a future change pushes p95 over 2x baseline, investigate before merging.
"""

import statistics
import time

import pytest

# These benchmarks need the full app stack (DB, license_service, etc.).
# They are skipped unless explicitly enabled, since CI doesn't always
# stand up the production-shape DB the app needs.
pytestmark = pytest.mark.skipif(
    True,
    reason="Bench-only; enable manually after standing up the test DB.",
)


def _percentiles(samples_ms):
    """Return (p50, p95) in milliseconds."""
    s = sorted(samples_ms)
    n = len(s)
    return s[n // 2], s[int(n * 0.95)]


def _bench(client, method, path, rounds=200):
    samples = []
    fn = getattr(client, method.lower())
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn(path)
        samples.append((time.perf_counter() - t0) * 1000.0)
    p50, p95 = _percentiles(samples)
    mean = statistics.mean(samples)
    return p50, p95, mean


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from backend.main import app

    return TestClient(app)


def test_bench_health(client):
    p50, p95, mean = _bench(client, "GET", "/api/health")
    print(f"\nGET /api/health: p50={p50:.2f}ms p95={p95:.2f}ms mean={mean:.2f}ms")
    assert p95 < 100, "p95 latency above 100ms suggests a regression"  # nosec B101


def test_bench_automation_list(client):
    p50, p95, mean = _bench(client, "GET", "/api/v1/automation/scripts")
    print(
        f"\nGET /api/v1/automation/scripts: "
        f"p50={p50:.2f}ms p95={p95:.2f}ms mean={mean:.2f}ms"
    )
    # 402 (no license) or 200 (empty list) are both fine — we're measuring
    # router + auth + license-check overhead, not data.
    assert p95 < 200  # nosec B101


def test_bench_fleet_list(client):
    p50, p95, mean = _bench(client, "GET", "/api/v1/fleet/groups")
    print(
        f"\nGET /api/v1/fleet/groups: "
        f"p50={p50:.2f}ms p95={p95:.2f}ms mean={mean:.2f}ms"
    )
    assert p95 < 200  # nosec B101
