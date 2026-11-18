# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pro+ licensed-stub route groups (part A) for :func:`mount_proplus_stub_routes`.

Extracted from ``backend.api.proplus_routes`` to keep every module under the
line-count cap.  ``mount_proplus_stub_routes`` (the public entry re-exported by
``proplus_routes``) lives here and delegates to the two group functions -- this
one (audit / secrets / container / reporting / av / firewall) and
``proplus_routes_stubs_extra._mount_stub_group_b`` (automation onward).

When a Pro+ module isn't licensed/loaded, every stub -- read or write --
answers 402 (503 when licensed but the engine is not loaded) through
``refuse_unlicensed``, so the frontend shows a clean "license required" state
instead of a 404.  Writes moved off ``200 {"licensed": false}`` first, because
a 200 told a script its deploy, delete or dispatch had worked; reads followed
(Phase 25 edition audit, 2026-11-14) so one status code means "unlicensed"
everywhere.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_bearer import get_current_user
from backend.licensing.feature_gate import refuse_unlicensed
from backend.i18n import _
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
    stubs_mounted += _mount_provisioning_stubs(app, results)
    stubs_mounted += _mount_backup_stubs(app, results)

    if stubs_mounted > 0:
        logger.info(
            "Mounted %d Pro+ stub route group(s) for unlicensed modules",
            stubs_mounted,
        )


def _mount_backup_stubs(app, results: dict) -> int:
    """402 for backup encryption (Phase 24.6) without backup_engine, for the
    same reason as the provisioning stubs: only a licensed UI calls these, so
    a caller that reaches them unlicensed is a script, and "it worked" (200)
    or "no such page" (404) would both mislead it."""
    if results.get("backup_engine"):
        return 0
    router = APIRouter(prefix="/v1/backup-encryption", tags=["backup-stubs"])

    def _unlicensed():
        return HTTPException(
            status_code=402,
            detail=_(
                "Encrypted backups require a SysManage Professional+ license "
                "with the backup engine. Please upgrade to access this feature."
            ),
        )

    # Every route the engine mounts under this prefix (backup_engine.pyx):
    # only the host ones were stubbed, so rotation, the rotation settings,
    # snapshot signing and the break-glass export answered 404 unlicensed
    # (edition audit, 2026-11-03).
    @router.get("/host/{host_id}")
    @router.post("/host/{host_id}")
    @router.post("/host/{host_id}/rotate")
    def backup_encryption_host_stub(
        host_id: str, current_user=Depends(get_current_user)
    ):
        del host_id
        raise _unlicensed()

    @router.get("/settings")
    @router.put("/settings")
    @router.get("/signing")
    @router.post("/signing")
    @router.post("/break-glass")
    def backup_encryption_stub(current_user=Depends(get_current_user)):
        raise _unlicensed()

    app.include_router(router, prefix="/api")
    logger.debug("Mounted backup engine 402 stub routes")
    return 1


def _mount_provisioning_stubs(app, results: dict) -> int:
    """Mount 402 stubs for the whole provisioning surface (Phase 18.1 + 18.2).

    These answer 402 like every other stub group.  The provisioning UI ships
    only in the Pro+ plugin, so nothing in the open-source frontend calls
    these; what does is a script or an operator with curl, and 402 with a
    reason is the honest answer -- the convention also used by the OSS-side
    gates in child_host_crud.py and airgap_collector_runs.py.

    Without these the endpoints simply are not mounted, so an unlicensed server
    answers 404 -- indistinguishable from a typo in the URL.

    Returns the number of stub route groups mounted.
    """
    if results.get("provisioning_engine"):
        return 0

    def _unlicensed():
        raise HTTPException(
            status_code=402,
            detail=_(
                "Host provisioning requires a SysManage Professional+ license "
                "with the provisioning engine. Please upgrade to access this "
                "feature."
            ),
        )

    router = APIRouter(prefix="/v1/provisioning", tags=["provisioning-stubs"])

    # 18.1 -- compute provisioning
    @router.get("/providers")
    @router.get("/compute-resources")
    @router.get("/templates")
    @router.get("/jobs")
    def provisioning_read_stub(current_user=Depends(get_current_user)):
        _unlicensed()

    @router.post("/compute-resources")
    @router.post("/templates")
    @router.post("/provision")
    def provisioning_write_stub(current_user=Depends(get_current_user)):
        _unlicensed()

    # 18.2 -- bare metal: catalog, per-MAC assignment, discovery, boot media
    @router.get("/install-sources")
    @router.get("/install-assignments")
    @router.get("/discovered-hosts")
    @router.get("/bootdisk/status")
    def baremetal_read_stub(current_user=Depends(get_current_user)):
        _unlicensed()

    @router.post("/install-sources")
    @router.post("/install-assignments")
    def baremetal_write_stub(current_user=Depends(get_current_user)):
        _unlicensed()

    app.include_router(router, prefix="/api")
    logger.debug("Mounted provisioning engine 402 stub routes")
    return 1


def _mount_stub_group_a(app, results: dict) -> int:
    """Mount licensed-stub routes for the audit / secrets / container /
    reporting / av_management / firewall_orchestration engines.  Returns the
    number of stub route groups mounted."""
    stubs_mounted = 0

    if not results.get("audit_engine"):
        router = APIRouter(prefix="/v1/audit", tags=["audit-stubs"])

        @router.get("/statistics")
        def audit_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("audit_engine")

        @router.post("/export")
        def audit_export_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("audit_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted audit engine stub routes")

    if not results.get("secrets_engine"):
        router = APIRouter(prefix="/v1/secrets", tags=["secrets-stubs"])

        @router.get("/statistics")
        def secrets_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.get("/access-logs")
        def secrets_access_logs_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.get("/rotation-schedules")
        def secrets_rotation_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.get("/{secret_id}/versions")
        def secrets_versions_stub(
            secret_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        # GPG Key Management relocated into the licensed secrets_engine (Pro+
        # moat).  Without the engine, these sub-paths serve the licensed-stub so
        # /api/v1/secrets/gpg-keys* answers 402 rather than 404.
        @router.get("/gpg-keys")
        def gpg_keys_list_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.post("/gpg-keys")
        def gpg_keys_upload_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.get("/gpg-keys/{key_id}")
        def gpg_keys_get_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.delete("/gpg-keys/{key_id}")
        def gpg_keys_delete_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.get("/gpg-keys/{key_id}/assignments")
        def gpg_keys_list_assignments_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.post("/gpg-keys/{key_id}/assignments")
        def gpg_keys_create_assignment_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        @router.delete("/gpg-keys/{key_id}/assignments/{assignment_id}")
        def gpg_keys_delete_assignment_stub(
            key_id: str,
            assignment_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("secrets_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted secrets engine stub routes")

    if not results.get("container_engine"):
        router = APIRouter(prefix="/v1/containers", tags=["container-stubs"])

        @router.get("/statistics")
        def containers_statistics_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("container_engine")

        @router.post("/create")
        def containers_create_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("container_engine")

        @router.post("/{container_id}/action")
        def containers_action_stub(
            container_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("container_engine")

        @router.post("/{container_id}/network")
        def containers_network_stub(
            container_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("container_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted container engine stub routes")

    if not results.get("reporting_engine"):
        router = APIRouter(prefix="/v1/reports", tags=["reporting-stubs"])

        @router.get("/generate/{report_type}")
        def reports_generate_stub(
            report_type: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("reporting_engine")

        @router.get("/view/{report_type}")
        def reports_view_stub(
            report_type: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("reporting_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted reporting engine stub routes")

    if not results.get("av_management_engine"):
        router = APIRouter(prefix="/v1/av", tags=["av-management-stubs"])

        @router.get("/status/{host_id}")
        def av_status_stub(
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.post("/deploy")
        def av_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.post("/uninstall")
        def av_uninstall_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.post("/scan")
        def av_scan_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.get("/commercial/fleet-report")
        def av_commercial_fleet_report_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.get("/policies")
        def av_list_policies_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.post("/policies")
        def av_create_policy_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        @router.post("/policies/{policy_id}/apply")
        def av_apply_policy_stub(
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("av_management_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted av_management_engine stub routes")

    if not results.get("firewall_orchestration_engine"):
        router = APIRouter(prefix="/v1/firewall", tags=["firewall-orchestration-stubs"])

        @router.get("/status/{host_id}")
        def fw_status_stub(
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.post("/deploy")
        def fw_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.get("/roles")
        def fw_list_roles_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.post("/roles")
        def fw_create_role_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.post("/compliance-check")
        def fw_compliance_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.post("/fleet/deploy")
        def fw_fleet_deploy_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        @router.get("/compliance/report")
        def fw_compliance_report_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("firewall_orchestration_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted firewall_orchestration_engine stub routes")

    return stubs_mounted
