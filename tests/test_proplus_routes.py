# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for backend.api.proplus_routes.

Covers:
- _feature_dependency / _module_dependency factories (decorator + Depends modes)
- mount_*_routes for every engine: not-loaded, provides_routes=False, exception, success
- mount_proplus_routes orchestration
- The stub routes registered when modules aren't loaded — driven via TestClient
"""

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
        # When no module is loaded, every key should be False and stubs get
        # mounted.  Multi-tenancy is gated on the ``multitenancy.enabled`` config
        # flag (not a loaded module), so pin it off here for the "all engines
        # off" case.
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=None
        ), patch("backend.config.config.is_multitenancy_enabled", return_value=False):
            results = proplus_routes.mount_proplus_routes(FastAPI())
        expected_keys = {
            "vuln_engine",
            "advisory_engine",
            "lifecycle_engine",
            "provisioning_engine",
            "health_engine",
            "compliance_engine",
            "alerting_engine",
            "reporting_engine",
            "audit_engine",
            "secrets_engine",
            "container_engine",
            "av_management_engine",
            "firewall_orchestration_engine",
            "automation_engine",
            "fleet_engine",
            "virtualization_engine",
            "observability_engine",
            "federation_controller_engine",
            "federation_site_engine",
            "multitenancy_engine",
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

    def test_automation_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/automation/scripts").json() == {
                "licensed": False,
                "scripts": [],
            }
            assert c.post("/api/v1/automation/scripts").json() == {"licensed": False}
            assert c.get("/api/v1/automation/executions").json() == {
                "licensed": False,
                "executions": [],
            }
            assert c.get("/api/v1/automation/approvals").json() == {
                "licensed": False,
                "approvals": [],
            }
            assert c.get("/api/v1/automation/schedules").json() == {
                "licensed": False,
                "schedules": [],
            }

    def test_fleet_stubs(self, stub_app):
        from fastapi.testclient import TestClient

        with TestClient(stub_app) as c:
            assert c.get("/api/v1/fleet/groups").json() == {
                "licensed": False,
                "groups": [],
            }
            assert c.post("/api/v1/fleet/groups").json() == {"licensed": False}
            assert c.post("/api/v1/fleet/select").json() == {
                "licensed": False,
                "host_ids": [],
                "count": 0,
            }
            assert c.post("/api/v1/fleet/bulk").json() == {"licensed": False}
            assert c.get("/api/v1/fleet/bulk").json() == {
                "licensed": False,
                "operations": [],
            }
            assert c.post("/api/v1/fleet/rolling").json() == {"licensed": False}
            assert c.get("/api/v1/fleet/rolling").json() == {
                "licensed": False,
                "deployments": [],
            }
            assert c.get("/api/v1/fleet/schedules").json() == {
                "licensed": False,
                "schedules": [],
            }


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
                "automation_engine": True,
                "fleet_engine": True,
                "virtualization_engine": True,
                "observability_engine": True,
                "federation_controller_engine": True,
                "federation_site_engine": True,
                # Phase 18 — the provisioning surface has 402 stubs too, so a
                # licensed server must not mount them either. This test caught
                # the omission when they were added, which is exactly its job.
                "provisioning_engine": True,
            },
        )
        assert len(app.routes) == before


class TestProvisioningSecretResolver:
    """The OpenBAO secret resolver injected into the provisioning router
    (Phase 18.1). Returns the stored field dict (the engine picks the fields it
    needs per provider kind), and fails safe to ambient SSH without leaking the
    ref."""

    def test_returns_field_dict_on_success(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            vault.return_value.retrieve_secret.return_value = {
                "private_key": "PRIVKEYDATA"
            }
            out = proplus_routes._provisioning_secret_resolver("secret/data/kvm")
        assert out == {"private_key": "PRIVKEYDATA"}

    def test_returns_proxmox_token_plus_node_key(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            vault.return_value.retrieve_secret.return_value = {
                "value": "root@pam!t=secret",
                "node_ssh_private_key": "NODEKEY",
            }
            out = proplus_routes._provisioning_secret_resolver("p")
        assert out["value"] == "root@pam!t=secret"
        assert out["node_ssh_private_key"] == "NODEKEY"

    def test_empty_secret_returns_none(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            vault.return_value.retrieve_secret.return_value = {}
            assert proplus_routes._provisioning_secret_resolver("p") is None

    def test_vault_error_falls_back_to_none(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            vault.return_value.retrieve_secret.side_effect = RuntimeError("down")
            assert proplus_routes._provisioning_secret_resolver("p") is None


class TestProvisioningSecretWriterDeleter:
    """The OpenBAO writer/deleter injected into the provisioning router
    (Phase 18.1 secret-capture): raw secrets pasted in the UI are written to a
    tenant-namespaced path on create and purged on delete."""

    def test_writer_stores_fields_and_returns_namespaced_path(self):
        with patch("backend.services.vault_service.VaultService") as vault, patch(
            "backend.persistence.tenant_context.get_active_tenant",
            return_value="tenant-abc",
        ), patch(
            "backend.services.vault_service.run_with_vault_retry",
            side_effect=lambda fn, *a, **k: fn(*a, **k),
        ):
            vault.return_value.mount_path = "secret"
            ref = proplus_routes._provisioning_secret_writer(
                "res-123", {"value": "tok", "node_ssh_private_key": "NK"}
            )
            assert ref == (
                "secret/data/sysmanage/tenant/tenant-abc/provisioning/res-123"
            )
            vault.return_value.make_raw_request.assert_called_once_with(
                "POST", ref, {"data": {"value": "tok", "node_ssh_private_key": "NK"}}
            )

    def test_writer_path_without_tenant(self):
        with patch("backend.services.vault_service.VaultService") as vault, patch(
            "backend.persistence.tenant_context.get_active_tenant",
            return_value=None,
        ), patch(
            "backend.services.vault_service.run_with_vault_retry",
            side_effect=lambda fn, *a, **k: fn(*a, **k),
        ):
            vault.return_value.mount_path = "secret"
            ref = proplus_routes._provisioning_secret_writer("res-1", {"value": "t"})
            assert ref == "secret/data/sysmanage/provisioning/res-1"

    def test_deleter_purges_our_namespace(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            proplus_routes._provisioning_secret_deleter(
                "secret/data/sysmanage/provisioning/res-9"
            )
            vault.return_value.delete_secret.assert_called_once_with(
                "secret/data/sysmanage/provisioning/res-9"
            )

    def test_deleter_skips_bring_your_own_path(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            proplus_routes._provisioning_secret_deleter("secret/data/shared/kvm")
            vault.return_value.delete_secret.assert_not_called()

    def test_deleter_swallows_vault_error(self):
        with patch("backend.services.vault_service.VaultService") as vault:
            vault.return_value.delete_secret.side_effect = RuntimeError("down")
            # must not raise (the row is already gone)
            proplus_routes._provisioning_secret_deleter(
                "secret/data/sysmanage/provisioning/res-9"
            )


class TestProvisioningRouterVersionSkew:
    """mount_provisioning_routes must survive an engine .so that predates the
    Phase 18.2 router seams.

    Regression: passing the 18.2 keywords unconditionally raised TypeError on an
    older ``provisioning_engine`` build, which failed the mount outright — and
    that also removed the 18.1 compute-provisioning routes the old .so DID
    support.  A whole feature area disappeared with only a stack trace in the
    log to explain it.
    """

    _NEW_KWARGS = (
        "dispatch_plan_fn",
        "register_correlation_fn",
        "boot_session_iterator_fn",
        "enrollment_token_fn",
    )

    def _engine(self, *, accepts_new):
        engine = MagicMock()
        engine.get_module_info.return_value = {
            "provides_routes": True,
            "version": "1.0.6",
        }

        def _factory(**kwargs):
            if not accepts_new:
                for name in self._NEW_KWARGS:
                    if name in kwargs:
                        raise TypeError(
                            "get_provisioning_router() got an unexpected "
                            "keyword argument %r" % name
                        )
            return MagicMock(name="router")

        engine.get_provisioning_router.side_effect = _factory
        return engine

    def test_old_engine_still_mounts_the_18_1_routes(self):
        app = MagicMock()
        with patch.object(
            proplus_routes.module_loader,
            "get_module",
            return_value=self._engine(accepts_new=False),
        ):
            assert proplus_routes.mount_provisioning_routes(app) is True
        app.include_router.assert_called_once()

    def test_old_engine_retry_drops_only_the_18_2_kwargs(self):
        app = MagicMock()
        engine = self._engine(accepts_new=False)
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            proplus_routes.mount_provisioning_routes(app)
        # First attempt with the seams, second without — and the 18.1 arguments
        # must survive the retry.
        assert engine.get_provisioning_router.call_count == 2
        retry_kwargs = engine.get_provisioning_router.call_args_list[1].kwargs
        for name in self._NEW_KWARGS:
            assert name not in retry_kwargs
        assert retry_kwargs["models"] is proplus_routes.models
        assert "secret_resolver" in retry_kwargs

    def test_new_engine_receives_the_18_2_seams(self):
        app = MagicMock()
        engine = self._engine(accepts_new=True)
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            assert proplus_routes.mount_provisioning_routes(app) is True
        assert engine.get_provisioning_router.call_count == 1
        kwargs = engine.get_provisioning_router.call_args.kwargs
        for name in self._NEW_KWARGS:
            assert name in kwargs

    def test_a_real_failure_still_reports_unmounted(self):
        """The fallback must not swallow genuine breakage."""
        app = MagicMock()
        engine = MagicMock()
        engine.get_module_info.return_value = {
            "provides_routes": True,
            "version": "1.0.7",
        }
        engine.get_provisioning_router.side_effect = RuntimeError("engine exploded")
        with patch.object(
            proplus_routes.module_loader, "get_module", return_value=engine
        ):
            assert proplus_routes.mount_provisioning_routes(app) is False


class TestProvisioningEnrollmentTokenSkew:
    """The token minter must not lose the whole token over an optional hint.

    Regression: ``site_id``/``access_group_id`` arrived with Phase 18.1 S4.  A
    ``multitenancy_engine`` built before that raises TypeError on them, the mint
    failed, no token reached the bootstrap — and a bare-metal host completed a
    25-minute install only to enroll with NO TENANT.  Enrolling into the right
    tenant without a site is strictly better than that, so degrade and warn.
    """

    def _mint(self, *, accepts_placement, **call_kwargs):
        calls = []

        def _generate_token(session, tenant_id, **kwargs):
            calls.append(kwargs)
            if not accepts_placement and (
                "site_id" in kwargs or "access_group_id" in kwargs
            ):
                raise TypeError(
                    "generate_token() got an unexpected keyword argument 'site_id'"
                )
            return "plaintext-token", MagicMock()

        cfg = MagicMock()
        cfg.is_multitenancy_enabled.return_value = True
        enrollment = MagicMock()
        enrollment.generate_token.side_effect = _generate_token

        with patch.dict(
            "sys.modules",
            {
                "backend.config": MagicMock(config=cfg),
                "backend.services": MagicMock(enrollment_service=enrollment),
            },
        ), patch("backend.persistence.partitions.partition_session"):
            token = proplus_routes._provisioning_enrollment_token_fn(
                tenant_id="tenant-1", hostname="pxe-1", **call_kwargs
            )
        return token, calls

    def test_current_engine_gets_the_placement(self):
        token, calls = self._mint(
            accepts_placement=True, site_id="site-9", access_group_id="ag-3"
        )
        assert token == "plaintext-token"
        assert len(calls) == 1
        assert calls[0]["site_id"] == "site-9"
        assert calls[0]["access_group_id"] == "ag-3"
        assert calls[0]["max_uses"] == 1

    def test_old_engine_still_yields_a_tenant_scoped_token(self):
        token, calls = self._mint(
            accepts_placement=False, site_id="site-9", access_group_id="ag-3"
        )
        # The point of the fix: a token, so the host lands in tenant-1 rather
        # than nowhere.
        assert token == "plaintext-token"
        assert len(calls) == 2  # first attempt raised, retry succeeded
        assert "site_id" not in calls[1]
        assert "access_group_id" not in calls[1]
        assert calls[1]["max_uses"] == 1
        assert calls[1]["created_by"] == "provisioning"

    def test_no_tenant_declines_rather_than_guessing(self):
        cfg = MagicMock()
        cfg.is_multitenancy_enabled.return_value = True
        with patch.dict("sys.modules", {"backend.config": MagicMock(config=cfg)}):
            assert (
                proplus_routes._provisioning_enrollment_token_fn(
                    tenant_id=None, hostname="pxe-1"
                )
                is None
            )
