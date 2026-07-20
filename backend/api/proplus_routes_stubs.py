# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pro+ licensed-stub route groups (part A) for :func:`mount_proplus_stub_routes`.

Extracted from ``backend.api.proplus_routes`` to keep every module under the
line-count cap.  ``mount_proplus_stub_routes`` (the public entry re-exported by
``proplus_routes``) lives here and delegates to the two group functions — this
one (audit / secrets / container / reporting / av / firewall) and
``proplus_routes_stubs_extra._mount_stub_group_b`` (automation onward).

When a Pro+ module isn't licensed/loaded, these stubs answer with
``{"licensed": false}`` and HTTP 200 so the frontend plugin shows a clean
"license required" message instead of a 404.
"""

from fastapi import APIRouter, Depends

from backend.auth.auth_bearer import get_current_user
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.proplus_routes")


def mount_proplus_stub_routes(app, results: dict) -> None:
    """Mount stub routes for Pro+ modules that weren't loaded.

    Delegates to the two group functions and logs the aggregate count.

    Args:
        app: The FastAPI application instance
        results: Dictionary of module mount results from mount_proplus_routes
    """
    from backend.api.proplus_routes_stubs_extra import _mount_stub_group_b

    stubs_mounted = _mount_stub_group_a(app, results)
    stubs_mounted += _mount_stub_group_b(app, results)

    if stubs_mounted > 0:
        logger.info(
            "Mounted %d Pro+ stub route group(s) for unlicensed modules",
            stubs_mounted,
        )


def _mount_stub_group_a(app, results: dict) -> int:
    """Mount licensed-stub routes for the audit / secrets / container /
    reporting / av_management / firewall_orchestration engines.  Returns the
    number of stub route groups mounted."""
    stubs_mounted = 0

    if not results.get("audit_engine"):
        router = APIRouter(prefix="/v1/audit", tags=["audit-stubs"])

        @router.get("/statistics")
        async def audit_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/export")
        async def audit_export_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted audit engine stub routes")

    if not results.get("secrets_engine"):
        router = APIRouter(prefix="/v1/secrets", tags=["secrets-stubs"])

        @router.get("/statistics")
        async def secrets_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/access-logs")
        async def secrets_access_logs_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "access_logs": []}

        @router.get("/rotation-schedules")
        async def secrets_rotation_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "schedules": []}

        @router.get("/{secret_id}/versions")
        async def secrets_versions_stub(
            secret_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "versions": []}

        # GPG Key Management relocated into the licensed secrets_engine (Pro+
        # moat).  Without the engine, these sub-paths serve the licensed-stub so
        # /api/v1/secrets/gpg-keys* returns {"licensed": False} rather than 404.
        @router.get("/gpg-keys")
        async def gpg_keys_list_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "gpg_keys": []}

        @router.post("/gpg-keys")
        async def gpg_keys_upload_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/gpg-keys/{key_id}")
        async def gpg_keys_get_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/gpg-keys/{key_id}")
        async def gpg_keys_delete_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/gpg-keys/{key_id}/assignments")
        async def gpg_keys_list_assignments_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "assignments": []}

        @router.post("/gpg-keys/{key_id}/assignments")
        async def gpg_keys_create_assignment_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/gpg-keys/{key_id}/assignments/{assignment_id}")
        async def gpg_keys_delete_assignment_stub(
            key_id: str,
            assignment_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted secrets engine stub routes")

    if not results.get("container_engine"):
        router = APIRouter(prefix="/v1/containers", tags=["container-stubs"])

        @router.get("/statistics")
        async def containers_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/create")
        async def containers_create_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/{container_id}/action")
        async def containers_action_stub(
            container_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/{container_id}/network")
        async def containers_network_stub(
            container_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted container engine stub routes")

    if not results.get("reporting_engine"):
        router = APIRouter(prefix="/v1/reports", tags=["reporting-stubs"])

        @router.get("/generate/{report_type}")
        async def reports_generate_stub(
            report_type: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/view/{report_type}")
        async def reports_view_stub(
            report_type: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted reporting engine stub routes")

    if not results.get("av_management_engine"):
        router = APIRouter(prefix="/v1/av", tags=["av-management-stubs"])

        @router.get("/status/{host_id}")
        async def av_status_stub(
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {
                "licensed": False,
                "host_id": host_id,
                "av_installed": False,
                "commercial_av_detected": [],
            }

        @router.post("/deploy")
        async def av_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/uninstall")
        async def av_uninstall_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/scan")
        async def av_scan_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/commercial/fleet-report")
        async def av_commercial_fleet_report_stub(
            current_user=Depends(get_current_user),
        ):
            return {
                "licensed": False,
                "total_hosts": 0,
                "hosts_with_commercial_av": 0,
                "by_product": {},
                "realtime_protection_off_count": 0,
                "entries": [],
            }

        @router.get("/policies")
        async def av_list_policies_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "policies": []}

        @router.post("/policies")
        async def av_create_policy_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/policies/{policy_id}/apply")
        async def av_apply_policy_stub(
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "policy_id": policy_id}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted av_management_engine stub routes")

    if not results.get("firewall_orchestration_engine"):
        router = APIRouter(prefix="/v1/firewall", tags=["firewall-orchestration-stubs"])

        @router.get("/status/{host_id}")
        async def fw_status_stub(
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {
                "licensed": False,
                "host_id": host_id,
                "firewall_type": None,
                "applied_roles": [],
            }

        @router.post("/deploy")
        async def fw_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/roles")
        async def fw_list_roles_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "roles": []}

        @router.post("/roles")
        async def fw_create_role_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/compliance-check")
        async def fw_compliance_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/fleet/deploy")
        async def fw_fleet_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            return {
                "licensed": False,
                "role_names": [],
                "queued_hosts": [],
                "skipped_hosts": [],
            }

        @router.get("/compliance/report")
        async def fw_compliance_report_stub(
            current_user=Depends(get_current_user),
        ):
            return {
                "licensed": False,
                "total_hosts": 0,
                "compliant_hosts": 0,
                "noncompliant_hosts": 0,
                "entries": [],
            }

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted firewall_orchestration_engine stub routes")

    return stubs_mounted
