# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pro+ licensed-stub route groups (part B) for :func:`mount_proplus_stub_routes`.

Extracted from ``backend.api.proplus_routes`` (with part A in
``proplus_routes_stubs``) to keep every module under the line-count cap.  Covers
the automation / fleet / virtualization / observability / federation engines.
"""

from fastapi import APIRouter, Depends

from backend.auth.auth_bearer import get_current_user
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.proplus_routes")


def _mount_stub_group_b(app, results: dict) -> int:
    """Mount licensed-stub routes for the automation / fleet / virtualization /
    observability / federation engines.  Returns the number of stub route
    groups mounted."""
    stubs_mounted = 0

    if not results.get("automation_engine"):
        router = APIRouter(prefix="/v1/automation", tags=["automation-stubs"])

        @router.get("/scripts")
        async def automation_list_scripts_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "scripts": []}

        @router.post("/scripts")
        async def automation_create_script_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/executions")
        async def automation_list_executions_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "executions": []}

        @router.get("/approvals")
        async def automation_list_approvals_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "approvals": []}

        @router.get("/schedules")
        async def automation_list_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "schedules": []}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted automation_engine stub routes")

    if not results.get("fleet_engine"):
        router = APIRouter(prefix="/v1/fleet", tags=["fleet-stubs"])

        @router.get("/groups")
        async def fleet_list_groups_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "groups": []}

        @router.post("/groups")
        async def fleet_create_group_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/select")
        async def fleet_select_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "host_ids": [], "count": 0}

        @router.post("/bulk")
        async def fleet_bulk_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/bulk")
        async def fleet_list_bulk_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "operations": []}

        @router.post("/rolling")
        async def fleet_rolling_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/rolling")
        async def fleet_list_rolling_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "deployments": []}

        @router.get("/schedules")
        async def fleet_list_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "schedules": []}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted fleet_engine stub routes")

    if not results.get("virtualization_engine"):
        router = APIRouter(prefix="/v1/virt", tags=["virtualization-stubs"])

        @router.post("/kvm/{host_id}/{vm_name}/{action}")
        async def virt_kvm_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/create")
        async def virt_kvm_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/{vm_name}/delete")
        async def virt_kvm_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/storage/download")
        async def virt_kvm_storage_download_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/network/create")
        async def virt_kvm_network_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/network/{name}/delete")
        async def virt_kvm_network_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            name: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/kvm/{host_id}/network/list")
        async def virt_kvm_network_list_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/bhyve/{host_id}/create")
        async def virt_bhyve_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/bhyve/{host_id}/{vm_name}/delete")
        async def virt_bhyve_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/bhyve/{host_id}/zvol/create")
        async def virt_bhyve_zvol_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/vmm/{host_id}/create")
        async def virt_vmm_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/vmm/{host_id}/{vm_name}/delete")
        async def virt_vmm_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/provision/{host_id}/{distro}")
        async def virt_provision_stub(  # pylint: disable=unused-argument
            host_id: str,
            distro: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/safe-reboot/{host_id}/prepare")
        async def virt_safe_reboot_prepare_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/safe-reboot/{host_id}/{hypervisor}/restore")
        async def virt_safe_reboot_restore_stub(  # pylint: disable=unused-argument
            host_id: str,
            hypervisor: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/bhyve/{host_id}/{vm_name}/{action}")
        async def virt_bhyve_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/vmm/{host_id}/{vm_name}/{action}")
        async def virt_vmm_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted virtualization_engine stub routes")

    if not results.get("observability_engine"):
        router = APIRouter(prefix="/v1/observability", tags=["observability-stubs"])

        @router.post("/otel/{host_id}/status")
        async def obs_otel_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/otel/{host_id}/deploy")
        async def obs_otel_deploy_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/otel/{host_id}/remove")
        async def obs_otel_remove_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/graylog/{host_id}/status")
        async def obs_graylog_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/graylog/{host_id}/deploy")
        async def obs_graylog_deploy_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/graylog/{host_id}/{platform}/remove")
        async def obs_graylog_remove_stub(  # pylint: disable=unused-argument
            host_id: str,
            platform: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/grafana/{host_id}/status")
        async def obs_grafana_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/grafana/{host_id}/provision")
        async def obs_grafana_provision_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/routing/{host_id}/apply")
        async def obs_routing_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # Custom Metrics & Graphs relocated into the licensed
        # observability_engine (Pro+ moat — Custom Metrics Slice 2).  Without
        # the engine, these sub-paths serve the licensed-stub so
        # /api/v1/observability/custom-metrics* returns {"licensed": False}
        # rather than 404.  Mirrors the gpg-keys stub template.
        @router.get("/custom-metrics")
        async def obs_custom_metrics_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "custom_metrics": []}

        @router.post("/custom-metrics")
        async def obs_custom_metrics_create_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/custom-metrics/{metric_id}")
        async def obs_custom_metrics_get_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.put("/custom-metrics/{metric_id}")
        async def obs_custom_metrics_update_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/custom-metrics/{metric_id}")
        async def obs_custom_metrics_delete_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.put("/custom-metrics/{metric_id}/tags")
        async def obs_custom_metrics_tags_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/custom-metrics/{metric_id}/samples")
        async def obs_custom_metrics_samples_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "samples": []}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted observability_engine stub routes")

    if not results.get("federation_controller_engine"):
        # 12.1.A surface — every endpoint here returns
        # ``{"licensed": False}`` until the Pro+ controller engine is
        # loaded.  Frontend (12.3) probes any of these to know whether
        # to render the federation UI.  When the engine loads, its own
        # router replaces these stubs (see ``mount_federation_controller_routes``).
        router = APIRouter(
            prefix="/v1/federation", tags=["federation-controller-stubs"]
        )

        # --- Sites registry --------------------------------------------------

        @router.get("/sites")
        async def fed_list_sites_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "sites": []}

        @router.post("/sites")
        async def fed_enroll_site_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/sites/enrollment/{token}/complete")
        async def fed_complete_enrollment_stub(  # pylint: disable=unused-argument
            token: str,
        ):
            # Phase 12.10 Slice 2.5: no ``Depends(get_current_user)``
            # here — the enrollment token IS the auth (chicken-and-egg
            # otherwise: site servers don't have JWT credentials with
            # the coordinator until enrollment completes).
            return {"licensed": False}

        @router.get("/sites/{site_id}")
        async def fed_site_detail_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.patch("/sites/{site_id}")
        async def fed_site_update_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/suspend")
        async def fed_site_suspend_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/resume")
        async def fed_site_resume_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/sites/{site_id}")
        async def fed_site_remove_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/sites/{site_id}/sync-status")
        async def fed_site_sync_status_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/sites/{site_id}/sync-timeline")
        async def fed_site_sync_timeline_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "events": []}

        # --- Cross-site host directory ---------------------------------------

        @router.get("/hosts")
        async def fed_hosts_search_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "hosts": []}

        @router.get("/hosts/{host_id}")
        async def fed_host_detail_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # --- Rollups ---------------------------------------------------------

        @router.get("/rollups/dashboard")
        async def fed_rollup_dashboard_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/reports/rollup")
        async def fed_reports_rollup_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "sites": [], "totals": {}}

        @router.get("/rollups/hosts")
        async def fed_rollup_hosts_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "rollups": []}

        @router.get("/rollups/compliance")
        async def fed_rollup_compliance_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "rollups": []}

        @router.get("/rollups/vulnerabilities")
        async def fed_rollup_vulnerabilities_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "rollups": []}

        # --- Policies --------------------------------------------------------

        @router.get("/policies")
        async def fed_list_policies_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "policies": []}

        @router.post("/policies")
        async def fed_create_policy_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/policies/{policy_id}")
        async def fed_policy_detail_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.patch("/policies/{policy_id}")
        async def fed_policy_update_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/policies/{policy_id}")
        async def fed_policy_deactivate_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/policies/{policy_id}/assign")
        async def fed_policy_assign_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/policies/{policy_id}/push")
        async def fed_policy_push_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/repush-policies")
        async def fed_site_repush_policies_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # --- Commands --------------------------------------------------------

        @router.post("/commands/dispatch")
        async def fed_command_dispatch_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/commands")
        async def fed_command_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "commands": []}

        @router.get("/commands/{command_id}")
        async def fed_command_detail_stub(  # pylint: disable=unused-argument
            command_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # --- Audit -----------------------------------------------------------

        @router.get("/audit")
        async def fed_audit_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "entries": []}

        @router.get("/audit/{entry_id}")
        async def fed_audit_detail_stub(  # pylint: disable=unused-argument
            entry_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # --- Rollup alerts ---------------------------------------------------

        @router.get("/alerts")
        async def fed_alerts_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "alerts": []}

        @router.post("/alerts/{alert_id}/acknowledge")
        async def fed_alert_ack_stub(  # pylint: disable=unused-argument
            alert_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/alert-config")
        async def fed_alert_config_get_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.put("/alert-config")
        async def fed_alert_config_put_stub(  # pylint: disable=unused-argument
            body: dict = None,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # Phase 12.5 — federation-aware dynamic-secret leases.
        @router.get("/secret-leases")
        async def fed_secret_leases_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "leases": []}

        @router.post("/secret-leases/{lease_id}/revoke")
        async def fed_secret_lease_revoke_stub(  # pylint: disable=unused-argument
            lease_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # Phase 12.6 ingest surface — endpoints sites POST data INTO
        # the coordinator over the federation wire protocol.  These
        # are authenticated by the site's long-lived sync bearer token
        # (NOT the operator's JWT), so they intentionally do NOT
        # ``Depends(get_current_user)`` — the stub layer just refuses
        # unlicensed access uniformly.

        @router.post("/sites/{site_id}/rollups/hosts")
        async def fed_ingest_host_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/rollups/compliance")
        async def fed_ingest_compliance_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/rollups/vulnerabilities")
        async def fed_ingest_vuln_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/host-directory")
        async def fed_ingest_host_directory_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/command-results")
        async def fed_ingest_command_results_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/metadata")
        async def fed_ingest_site_metadata_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        @router.post("/sites/{site_id}/secret-lease-requests")
        async def fed_ingest_secret_lease_request_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            return {"licensed": False}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted federation_controller_engine stub routes")

    if not results.get("federation_site_engine"):
        # 12.2 surface — endpoints the *coordinator* calls on the
        # site server.  Distinct prefix from the controller's outbound
        # surface (``/api/v1/federation/*``) so a server running as
        # both roles (test fixture, never production) keeps them
        # cleanly separated.
        router = APIRouter(
            prefix="/v1/federation/site",
            tags=["federation-site-stubs"],
        )

        # --- Enrollment handshake (site side) -----------------------------

        @router.post("/enroll")
        async def fed_site_enroll_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/enrollment-status")
        async def fed_site_enrollment_status_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "status": "unknown"}

        # --- Inbound: coordinator → site ---------------------------------

        @router.post("/policies")
        async def fed_site_receive_policy_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/commands")
        async def fed_site_receive_command_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.post("/secret-leases")
        async def fed_site_receive_secret_lease_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        # --- Site → operator: status surface -----------------------------

        @router.get("/sync-status")
        async def fed_site_engine_sync_status_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/sync-queue/depth")
        async def fed_site_queue_depth_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "depth": 0}

        @router.get("/received-policies")
        async def fed_site_received_policies_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "policies": []}

        @router.get("/received-commands")
        async def fed_site_received_commands_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "commands": []}

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted federation_site_engine stub routes")

    return stubs_mounted
