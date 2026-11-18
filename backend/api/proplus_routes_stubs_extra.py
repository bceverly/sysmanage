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
from backend.licensing.feature_gate import refuse_unlicensed
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
        def automation_list_scripts_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("automation_engine")

        @router.post("/scripts")
        def automation_create_script_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("automation_engine")

        @router.get("/executions")
        def automation_list_executions_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("automation_engine")

        @router.get("/approvals")
        def automation_list_approvals_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("automation_engine")

        @router.get("/schedules")
        def automation_list_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("automation_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted automation_engine stub routes")

    if not results.get("fleet_engine"):
        router = APIRouter(prefix="/v1/fleet", tags=["fleet-stubs"])

        @router.get("/groups")
        def fleet_list_groups_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.post("/groups")
        def fleet_create_group_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.post("/select")
        def fleet_select_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.post("/bulk")
        def fleet_bulk_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.get("/bulk")
        def fleet_list_bulk_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.post("/rolling")
        def fleet_rolling_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.get("/rolling")
        def fleet_list_rolling_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        @router.get("/schedules")
        def fleet_list_schedules_stub(
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("fleet_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted fleet_engine stub routes")

    if not results.get("virtualization_engine"):
        router = APIRouter(prefix="/v1/virt", tags=["virtualization-stubs"])

        @router.post("/kvm/{host_id}/{vm_name}/{action}")
        def virt_kvm_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/create")
        def virt_kvm_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/{vm_name}/delete")
        def virt_kvm_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/storage/download")
        def virt_kvm_storage_download_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/network/create")
        def virt_kvm_network_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/network/{name}/delete")
        def virt_kvm_network_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            name: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/kvm/{host_id}/network/list")
        def virt_kvm_network_list_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/bhyve/{host_id}/create")
        def virt_bhyve_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/bhyve/{host_id}/{vm_name}/delete")
        def virt_bhyve_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/bhyve/{host_id}/zvol/create")
        def virt_bhyve_zvol_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/vmm/{host_id}/create")
        def virt_vmm_create_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/vmm/{host_id}/{vm_name}/delete")
        def virt_vmm_delete_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/provision/{host_id}/{distro}")
        def virt_provision_stub(  # pylint: disable=unused-argument
            host_id: str,
            distro: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/safe-reboot/{host_id}/prepare")
        def virt_safe_reboot_prepare_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/safe-reboot/{host_id}/{hypervisor}/restore")
        def virt_safe_reboot_restore_stub(  # pylint: disable=unused-argument
            host_id: str,
            hypervisor: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/bhyve/{host_id}/{vm_name}/{action}")
        def virt_bhyve_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        @router.post("/vmm/{host_id}/{vm_name}/{action}")
        def virt_vmm_stub(  # pylint: disable=unused-argument
            host_id: str,
            vm_name: str,
            action: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("virtualization_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted virtualization_engine stub routes")

    if not results.get("observability_engine"):
        router = APIRouter(prefix="/v1/observability", tags=["observability-stubs"])

        @router.post("/otel/{host_id}/status")
        def obs_otel_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/otel/{host_id}/deploy")
        def obs_otel_deploy_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/otel/{host_id}/remove")
        def obs_otel_remove_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/graylog/{host_id}/status")
        def obs_graylog_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/graylog/{host_id}/deploy")
        def obs_graylog_deploy_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/graylog/{host_id}/{platform}/remove")
        def obs_graylog_remove_stub(  # pylint: disable=unused-argument
            host_id: str,
            platform: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/grafana/{host_id}/status")
        def obs_grafana_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/grafana/{host_id}/provision")
        def obs_grafana_provision_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/routing/{host_id}/apply")
        def obs_routing_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        # Custom Metrics & Graphs relocated into the licensed
        # observability_engine (Pro+ moat -- Custom Metrics Slice 2).  Without
        # the engine, these sub-paths serve the licensed-stub so
        # /api/v1/observability/custom-metrics* answers 402 rather than
        # 404.  Mirrors the gpg-keys stub template.
        @router.get("/custom-metrics")
        def obs_custom_metrics_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.post("/custom-metrics")
        def obs_custom_metrics_create_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.get("/custom-metrics/{metric_id}")
        def obs_custom_metrics_get_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.put("/custom-metrics/{metric_id}")
        def obs_custom_metrics_update_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.delete("/custom-metrics/{metric_id}")
        def obs_custom_metrics_delete_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.put("/custom-metrics/{metric_id}/tags")
        def obs_custom_metrics_tags_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.get("/custom-metrics/{metric_id}/samples")
        def obs_custom_metrics_samples_stub(  # pylint: disable=unused-argument
            metric_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        # Built-in host metric graphs (Phase 21.5) -- the read side lives in
        # observability_engine; unlicensed, the paths answer "not licensed".
        @router.get("/host-metrics/hosts/{host_id}")
        def obs_host_metrics_host_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        @router.get("/host-metrics/fleet/{key}")
        def obs_host_metrics_fleet_stub(  # pylint: disable=unused-argument
            key: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("observability_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted observability_engine stub routes")

    if not results.get("federation_controller_engine"):
        # 12.1.A surface -- every endpoint here answers 402 until the
        # Pro+ controller engine is loaded.  Frontend (12.3) probes any of these to know whether
        # to render the federation UI.  When the engine loads, its own
        # router replaces these stubs (see ``mount_federation_controller_routes``).
        router = APIRouter(
            prefix="/v1/federation", tags=["federation-controller-stubs"]
        )

        # --- Sites registry --------------------------------------------------

        @router.get("/sites")
        def fed_list_sites_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites")
        def fed_enroll_site_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/enrollment/{token}/complete")
        def fed_complete_enrollment_stub(  # pylint: disable=unused-argument
            token: str,
        ):
            # Phase 12.10 Slice 2.5: no ``Depends(get_current_user)``
            # here -- the enrollment token IS the auth (chicken-and-egg
            # otherwise: site servers don't have JWT credentials with
            # the coordinator until enrollment completes).
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/sites/{site_id}")
        def fed_site_detail_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.patch("/sites/{site_id}")
        def fed_site_update_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/suspend")
        def fed_site_suspend_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/resume")
        def fed_site_resume_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.delete("/sites/{site_id}")
        def fed_site_remove_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/sites/{site_id}/sync-status")
        def fed_site_sync_status_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/sites/{site_id}/sync-timeline")
        def fed_site_sync_timeline_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Cross-site host directory ---------------------------------------

        @router.get("/hosts")
        def fed_hosts_search_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/hosts/{host_id}")
        def fed_host_detail_stub(  # pylint: disable=unused-argument
            host_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Rollups ---------------------------------------------------------

        @router.get("/rollups/dashboard")
        def fed_rollup_dashboard_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/reports/rollup")
        def fed_reports_rollup_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/rollups/hosts")
        def fed_rollup_hosts_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/rollups/compliance")
        def fed_rollup_compliance_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/rollups/vulnerabilities")
        def fed_rollup_vulnerabilities_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Policies --------------------------------------------------------

        @router.get("/policies")
        def fed_list_policies_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/policies")
        def fed_create_policy_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/policies/{policy_id}")
        def fed_policy_detail_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.patch("/policies/{policy_id}")
        def fed_policy_update_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.delete("/policies/{policy_id}")
        def fed_policy_deactivate_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/policies/{policy_id}/assign")
        def fed_policy_assign_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/policies/{policy_id}/push")
        def fed_policy_push_stub(  # pylint: disable=unused-argument
            policy_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/repush-policies")
        def fed_site_repush_policies_stub(  # pylint: disable=unused-argument
            site_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Commands --------------------------------------------------------

        @router.post("/commands/dispatch")
        def fed_command_dispatch_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/commands")
        def fed_command_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/commands/{command_id}")
        def fed_command_detail_stub(  # pylint: disable=unused-argument
            command_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Audit -----------------------------------------------------------

        @router.get("/audit")
        def fed_audit_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/audit/{entry_id}")
        def fed_audit_detail_stub(  # pylint: disable=unused-argument
            entry_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # --- Rollup alerts ---------------------------------------------------

        @router.get("/alerts")
        def fed_alerts_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/alerts/{alert_id}/acknowledge")
        def fed_alert_ack_stub(  # pylint: disable=unused-argument
            alert_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.get("/alert-config")
        def fed_alert_config_get_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.put("/alert-config")
        def fed_alert_config_put_stub(  # pylint: disable=unused-argument
            body: dict = None,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # Phase 12.5 -- federation-aware dynamic-secret leases.
        @router.get("/secret-leases")
        def fed_secret_leases_list_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/secret-leases/{lease_id}/revoke")
        def fed_secret_lease_revoke_stub(  # pylint: disable=unused-argument
            lease_id: str,
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_controller_engine")

        # Phase 12.6 ingest surface -- endpoints sites POST data INTO
        # the coordinator over the federation wire protocol.  These
        # are authenticated by the site's long-lived sync bearer token
        # (NOT the operator's JWT), so they intentionally do NOT
        # ``Depends(get_current_user)`` -- the stub layer just refuses
        # unlicensed access uniformly.

        @router.post("/sites/{site_id}/rollups/hosts")
        def fed_ingest_host_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/rollups/compliance")
        def fed_ingest_compliance_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/rollups/vulnerabilities")
        def fed_ingest_vuln_rollup_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/host-directory")
        def fed_ingest_host_directory_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/command-results")
        def fed_ingest_command_results_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/metadata")
        def fed_ingest_site_metadata_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        @router.post("/sites/{site_id}/secret-lease-requests")
        def fed_ingest_secret_lease_request_stub(  # pylint: disable=unused-argument
            site_id: str,
        ):
            raise refuse_unlicensed("federation_controller_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted federation_controller_engine stub routes")

    if not results.get("federation_site_engine"):
        # 12.2 surface -- endpoints the *coordinator* calls on the
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
        def fed_site_enroll_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.get("/enrollment-status")
        def fed_site_enrollment_status_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        # --- Inbound: coordinator → site ---------------------------------

        @router.post("/policies")
        def fed_site_receive_policy_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.post("/commands")
        def fed_site_receive_command_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.post("/secret-leases")
        def fed_site_receive_secret_lease_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        # --- Site → operator: status surface -----------------------------

        @router.get("/sync-status")
        def fed_site_engine_sync_status_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.get("/sync-queue/depth")
        def fed_site_queue_depth_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.get("/received-policies")
        def fed_site_received_policies_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        @router.get("/received-commands")
        def fed_site_received_commands_stub(  # pylint: disable=unused-argument
            current_user=Depends(get_current_user),
        ):
            raise refuse_unlicensed("federation_site_engine")

        app.include_router(router, prefix="/api")
        stubs_mounted += 1
        logger.debug("Mounted federation_site_engine stub routes")

    return stubs_mounted
