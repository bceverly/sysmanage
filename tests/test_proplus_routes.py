"""
Tests for backend.api.proplus_routes.

Covers:
- _feature_dependency / _module_dependency factories (decorator + Depends modes)
- mount_*_routes for every engine: not-loaded, provides_routes=False, exception, success
- mount_proplus_routes orchestration
- The stub routes registered when modules aren't loaded — driven via TestClient
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException

from backend.api import proplus_routes

# ---------------------------------------------------------------------------
# _feature_dependency
# ---------------------------------------------------------------------------


class TestFeatureDependency:
    def test_dependency_mode_passes_when_feature_present(self):
        """Calling the gate with no args should not raise when license has feature."""
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=True
        ):
            from backend.licensing.features import FeatureCode

            gate = proplus_routes._feature_dependency(FeatureCode.HEALTH_ANALYSIS)
            # Dependency mode (no func arg) — runs the check.
            gate()  # should not raise

    def test_dependency_mode_raises_when_feature_missing(self):
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=False
        ):
            from backend.licensing.features import FeatureCode

            gate = proplus_routes._feature_dependency(FeatureCode.HEALTH_ANALYSIS)
            with pytest.raises(HTTPException) as exc:
                gate()
            assert exc.value.status_code == 403
            assert exc.value.detail["error"] == "pro_plus_required"

    def test_decorator_mode_wraps_sync_function(self):
        """When called with a function arg, returns a wrapped version."""
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=True
        ):
            gate = proplus_routes._feature_dependency("health")

            @gate
            def my_endpoint(value):
                return value * 2

            assert my_endpoint(21) == 42

    def test_decorator_mode_blocks_sync_function_without_license(self):
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=False
        ):
            gate = proplus_routes._feature_dependency("health")

            @gate
            def my_endpoint():
                return "should not run"

            with pytest.raises(HTTPException):
                my_endpoint()

    @pytest.mark.asyncio
    async def test_decorator_mode_wraps_async_function(self):
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=True
        ):
            gate = proplus_routes._feature_dependency("health")

            @gate
            async def my_endpoint(x):
                return x + 1

            assert await my_endpoint(5) == 6

    @pytest.mark.asyncio
    async def test_decorator_mode_blocks_async_function_without_license(self):
        with patch.object(
            proplus_routes.license_service, "has_feature", return_value=False
        ):
            gate = proplus_routes._feature_dependency("health")

            @gate
            async def my_endpoint():
                return "blocked"

            with pytest.raises(HTTPException):
                await my_endpoint()

    def test_signature_has_zero_params(self):
        """The injected __signature__ ensures FastAPI doesn't add a query param."""
        gate = proplus_routes._feature_dependency("health")
        import inspect

        sig = inspect.signature(gate)
        assert len(sig.parameters) == 0


# ---------------------------------------------------------------------------
# _module_dependency
# ---------------------------------------------------------------------------


class TestModuleDependency:
    def test_passes_when_module_loaded_and_licensed(self):
        with patch.object(
            proplus_routes.license_service, "has_module", return_value=True
        ), patch.object(
            proplus_routes.module_loader, "is_module_loaded", return_value=True
        ):
            gate = proplus_routes._module_dependency("health_engine")
            gate()  # no raise

    def test_raises_when_module_not_licensed(self):
        with patch.object(
            proplus_routes.license_service, "has_module", return_value=False
        ):
            gate = proplus_routes._module_dependency("health_engine")
            with pytest.raises(HTTPException) as exc:
                gate()
            assert exc.value.status_code == 403

    def test_raises_when_module_licensed_but_not_loaded(self):
        with patch.object(
            proplus_routes.license_service, "has_module", return_value=True
        ), patch.object(
            proplus_routes.module_loader, "is_module_loaded", return_value=False
        ):
            gate = proplus_routes._module_dependency("health_engine")
            with pytest.raises(HTTPException):
                gate()


# ---------------------------------------------------------------------------
# mount_*_routes — each follows same not-loaded / provides=False / exception / ok pattern
# ---------------------------------------------------------------------------


def _fake_engine_with_router(provides_routes=True):
    engine = MagicMock()
    engine.get_module_info.return_value = {
        "provides_routes": provides_routes,
        "version": "1.0.0",
    }
    # Each engine has its own router-factory method name; FastAPI's include_router
    # accepts any APIRouter, so we just hand back a real one.
    from fastapi import APIRouter

    router = APIRouter()
    # The routers that get_*_router returns are stored on a generic attribute
    # so the mount functions all reach for them with different names.  Stub
    # every plausible factory to return our router.
    for factory in (
        "get_vulnerability_router",
        "get_health_router",
        "get_compliance_router",
        "get_alerting_router",
        "get_reporting_router",
        "get_audit_router",
        "get_secrets_router",
        "get_container_router",
        "get_av_management_router",
        "get_firewall_orchestration_router",
    ):
        setattr(engine, factory, MagicMock(return_value=router))
    return engine


@pytest.mark.parametrize(
    "fn_name,module_code",
    [
        ("mount_vulnerability_routes", "vuln_engine"),
        ("mount_health_routes", "health_engine"),
        ("mount_compliance_routes", "compliance_engine"),
        ("mount_alerting_routes", "alerting_engine"),
        ("mount_reporting_routes", "reporting_engine"),
        ("mount_audit_routes", "audit_engine"),
        ("mount_secrets_routes", "secrets_engine"),
        ("mount_container_routes", "container_engine"),
        ("mount_av_management_routes", "av_management_engine"),
        ("mount_firewall_orchestration_routes", "firewall_orchestration_engine"),
    ],
)
class TestMountRoutes:
    def test_returns_false_when_module_not_loaded(self, fn_name, module_code):
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=None
        ):
            assert getattr(proplus_routes, fn_name)(FastAPI()) is False

    def test_returns_false_when_module_does_not_provide_routes(
        self, fn_name, module_code
    ):
        engine = _fake_engine_with_router(provides_routes=False)
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            assert getattr(proplus_routes, fn_name)(FastAPI()) is False

    def test_returns_false_when_router_factory_raises(self, fn_name, module_code):
        engine = _fake_engine_with_router()
        # Make the corresponding router factory raise.
        for attr in dir(engine):
            if attr.startswith("get_") and attr.endswith("_router"):
                getattr(engine, attr).side_effect = RuntimeError("boom")
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            assert getattr(proplus_routes, fn_name)(FastAPI()) is False

    def test_returns_true_on_successful_mount(self, fn_name, module_code):
        engine = _fake_engine_with_router()
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            assert getattr(proplus_routes, fn_name)(FastAPI()) is True


# ---------------------------------------------------------------------------
# mount_proplus_routes orchestration
# ---------------------------------------------------------------------------


class TestMountProplusRoutes:
    def test_returns_dict_with_all_engine_keys(self):
        # When no module is loaded, every key should be False and stubs get mounted.
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=None
        ):
            results = proplus_routes.mount_proplus_routes(FastAPI())
        expected_keys = {
            "vuln_engine",
            "health_engine",
            "compliance_engine",
            "alerting_engine",
            "reporting_engine",
            "audit_engine",
            "secrets_engine",
            "container_engine",
            "av_management_engine",
            "firewall_orchestration_engine",
        }
        assert set(results.keys()) == expected_keys
        assert all(v is False for v in results.values())

    def test_mounts_stubs_for_unloaded_modules(self):
        """When all modules are unloaded, mount_proplus_stub_routes is called
        with the all-False results dict and the stubs get added to the app."""
        app = FastAPI()
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=None
        ):
            proplus_routes.mount_proplus_routes(app)
        # The stub mounts add /api/v1/audit/statistics among many others.
        paths = {r.path for r in app.routes}
        assert "/api/v1/audit/statistics" in paths
        assert "/api/v1/secrets/statistics" in paths
        assert "/api/v1/firewall/status/{host_id}" in paths


# ---------------------------------------------------------------------------
# Stub endpoints — exercised through TestClient on a dedicated mini-app
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_app():
    """A bare FastAPI app with all Pro+ stubs mounted (no module loaded)."""
    app = FastAPI()
    # Bypass JWT for these stub tests.
    from backend.auth.auth_bearer import get_current_user

    app.dependency_overrides[get_current_user] = lambda: "test-user"
    proplus_routes.mount_proplus_stub_routes(
        app,
        {
            "audit_engine": False,
            "secrets_engine": False,
            "container_engine": False,
            "reporting_engine": False,
            "av_management_engine": False,
            "firewall_orchestration_engine": False,
        },
    )
    return app


class TestStubEndpoints:
    def test_audit_statistics_stub(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/audit/statistics").json() == {"licensed": False}
            assert c.post("/api/v1/audit/export").json() == {"licensed": False}

    def test_secrets_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/secrets/statistics").json()["licensed"] is False
            assert c.get("/api/v1/secrets/access-logs").json()["access_logs"] == []
            assert c.get("/api/v1/secrets/rotation-schedules").json()["schedules"] == []
            assert c.get("/api/v1/secrets/abc/versions").json()["versions"] == []

    def test_container_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/containers/statistics").json() == {"licensed": False}
            assert c.post("/api/v1/containers/create").json() == {"licensed": False}
            assert c.post("/api/v1/containers/abc/action").json() == {"licensed": False}
            assert c.post("/api/v1/containers/abc/network").json() == {
                "licensed": False
            }

    def test_reporting_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/reports/generate/foo").json() == {"licensed": False}
            assert c.get("/api/v1/reports/view/foo").json() == {"licensed": False}

    def test_av_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            body = c.get("/api/v1/av/status/host-1").json()
            assert body["licensed"] is False
            assert body["host_id"] == "host-1"
            assert c.post("/api/v1/av/deploy").json() == {"licensed": False}
            assert c.post("/api/v1/av/uninstall").json() == {"licensed": False}
            assert c.post("/api/v1/av/scan").json() == {"licensed": False}
            fleet = c.get("/api/v1/av/commercial/fleet-report").json()
            assert fleet["licensed"] is False
            assert fleet["entries"] == []
            assert c.get("/api/v1/av/policies").json() == {
                "licensed": False,
                "policies": [],
            }
            assert c.post("/api/v1/av/policies").json() == {"licensed": False}
            apply_resp = c.post("/api/v1/av/policies/p1/apply").json()
            assert apply_resp == {"licensed": False, "policy_id": "p1"}

    def test_firewall_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            status_body = c.get("/api/v1/firewall/status/h1").json()
            assert status_body["licensed"] is False
            assert status_body["applied_roles"] == []
            assert c.post("/api/v1/firewall/deploy").json() == {"licensed": False}
            assert c.get("/api/v1/firewall/roles").json()["roles"] == []
            assert c.post("/api/v1/firewall/roles").json() == {"licensed": False}
            assert c.post("/api/v1/firewall/compliance-check").json() == {
                "licensed": False
            }
            fleet = c.post("/api/v1/firewall/fleet/deploy").json()
            assert fleet["licensed"] is False
            assert fleet["queued_hosts"] == []
            report = c.get("/api/v1/firewall/compliance/report").json()
            assert report["total_hosts"] == 0


class TestStubsSkippedWhenModuleLoaded:
    def test_no_stubs_when_all_loaded(self):
        """If all modules are flagged as loaded, mount_proplus_stub_routes
        should add zero routes."""
        app = FastAPI()
        before = len(app.routes)
        proplus_routes.mount_proplus_stub_routes(
            app,
            {
                "audit_engine": True,
                "secrets_engine": True,
                "container_engine": True,
                "reporting_engine": True,
                "av_management_engine": True,
                "firewall_orchestration_engine": True,
            },
        )
        assert len(app.routes) == before
