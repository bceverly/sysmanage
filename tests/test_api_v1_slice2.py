"""
Phase 13.2.1 — Slice 2 native ``/api/v1`` migration (hosts / fleet).

Verifies the dual-surface contract for the migrated routers (fleet, host auth,
host_hostname, child_host, reboot_orchestration): representative endpoints
resolve identically under ``/api/v1`` and the deprecated ``/api`` alias.

Also pins the invariant that the agent-facing ``/host/register`` is NOT
versioned (it stays a stable unversioned contract for the fleet).
"""

import pytest

DUAL_SURFACE_PATHS = [
    "/fleet/status",
    "/fleet/agents",
    "/hosts",
    "/child-host-distributions",
]


class TestDualSurface:
    @pytest.mark.parametrize("path", DUAL_SURFACE_PATHS)
    def test_v1_and_alias_match(self, client, path):
        v1 = client.get("/api/v1" + path)
        alias = client.get("/api" + path)
        assert v1.status_code != 404, f"/api/v1{path} should be native"
        assert alias.status_code == 404, f"/api{path} alias retired (bridge removed)"

    @pytest.mark.parametrize("path", DUAL_SURFACE_PATHS)
    def test_v1_is_native(self, client, path):
        assert client.get("/api/v1" + path).status_code == 200


class TestAgentEndpointStaysUnversioned:
    """/host/register is agent-facing — it must stay a stable unversioned route.

    (The v1→legacy bridge may still *serve* /api/v1/host/register at runtime,
    but that's incidental; the contract is that there is no NATIVE v1 route, so
    the migration never moved the agent registration endpoint.)
    """

    def test_register_not_natively_versioned(self):
        import backend.main as m  # noqa: PLC0415

        paths = {r.path for r in m.app.routes if hasattr(r, "path")}
        assert "/api/host/register" in paths  # unversioned contract present
        assert "/api/v1/host/register" not in paths  # never natively versioned
