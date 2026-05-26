"""
Route registration module for the SysManage server.

This module provides functions to register all API routes including both
authenticated and unauthenticated endpoints.
"""

from fastapi import FastAPI

from backend.api import (
    access_groups,
    agent,
    airgap_bundles,
    airgap_collection_schedule,
    airgap_collector_runs,
    airgap_repository_buckets,
    airgap_repository_list,
    antivirus_defaults,
    antivirus_status,
    audit_log,
    auth,
    auth_mfa,
    broadcast,
    certificates,
    child_host,
    commercial_antivirus_status,
    config_management,
    cve_refresh_settings,
    default_repositories,
    diagnostics,
    dynamic_secrets,
    email,
    enabled_package_managers,
    external_idp,
    firewall_roles,
    firewall_status,
    fleet,
    grafana_integration,
    graylog_integration,
    license_management,
    host,
    host_hostname,
    openbao,
    opentelemetry,
    package_compliance,
    packages,
    password_reset,
    plugin_bundle,
    profile,
    queue,
    reboot_orchestration,
    report_branding,
    report_templates,
    reports,
    repository_mirroring,
    scripts,
    secrets,
    security,
    security_roles,
    server_info,
    tag,
    telemetry,
    third_party_repos,
    ubuntu_pro_settings,
    updates,
    upgrade_profiles,
    user,
    user_preferences,
)
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.routes")


def register_routes(app: FastAPI):
    """
    Register all API routes with the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    logger.debug("=== REGISTERING ROUTES ===")

    # Unauthenticated routes (no /api prefix)
    logger.debug("Registering unauthenticated routes:")

    logger.debug("Adding auth router with /api prefix")
    app.include_router(
        auth.router, prefix="/api"
    )  # /api/login, /api/refresh, /api/logout
    logger.debug("Auth router added")

    logger.debug(
        "Adding MFA router (no prefix — endpoints carry their own /api/auth prefix)"
    )
    app.include_router(auth_mfa.router)  # /api/auth/mfa/* + /api/settings/mfa
    logger.debug("MFA router added")

    # Phase 11 server-info — public, unauthenticated.  Lets the frontend
    # render the role chip + monitoring identify the box without login.
    app.include_router(server_info.router)
    logger.debug("Server-info router added")

    # Phase 11 B2 — air-gap collection schedules.  Routes are
    # license-gated (collector engine) at the handler level, so it's
    # safe to mount on every server (the gate returns 402 on standard
    # / repository roles).
    app.include_router(airgap_collection_schedule.router)
    logger.debug("Air-gap collection schedule router added")

    # Phase 11 — one-shot collector runs (ad-hoc UI-triggered).  Same
    # license-gate-at-handler pattern as the schedules router; safe to
    # mount unconditionally because the handler returns 402 on non-
    # collector deployments.
    app.include_router(airgap_collector_runs.router)
    logger.debug("Air-gap collector runs router added")

    # Phase 11 B5 — host-scoped compliance bucket endpoint that feeds
    # the AirgapComplianceBucketsCard frontend component.
    app.include_router(airgap_repository_buckets.router)
    logger.debug("Air-gap repository buckets router added")

    # Phase 11 B6 — list-all-repos + freshness endpoints feeding the
    # AirgapRepositories dashboard and RepositoryFreshnessCard.
    app.include_router(airgap_repository_list.router)
    logger.debug("Air-gap repository list router added")

    logger.debug(
        "Adding repository mirroring router (no prefix — endpoints carry /api prefix)"
    )
    app.include_router(repository_mirroring.router)
    logger.debug("Repository mirroring router added")

    logger.debug(
        "Adding external IdP router (no prefix — endpoints carry their own /api prefix)"
    )
    app.include_router(external_idp.router)
    logger.debug("External IdP router added")

    logger.debug("Adding agent public router with /api prefix")
    app.include_router(
        agent.public_router, prefix="/api"
    )  # /api/agent/auth (no auth required)
    logger.debug("Agent public router added")

    logger.debug("Adding agent authenticated router with /api prefix")
    app.include_router(
        agent.router, prefix="/api"
    )  # /api/agent/connect, /api/agent/installation-complete
    logger.debug("Agent authenticated router added")

    logger.debug("Adding host public router with /api prefix")
    app.include_router(
        host.public_router, prefix="/api"
    )  # /api/host/register (no auth)
    logger.debug("Host public router added")

    logger.debug("Adding certificates public router with /api prefix")
    app.include_router(
        certificates.public_router, prefix="/api"
    )  # /api/certificates/server-fingerprint, /api/certificates/ca-certificate (no auth)
    logger.debug("Certificates public router added")

    logger.debug("Adding password reset router with /api prefix")
    app.include_router(
        password_reset.router, prefix="/api"
    )  # /api/forgot-password, /api/reset-password, /api/validate-reset-token (no auth)
    logger.debug("Password reset router added")

    # Secure routes (with /api prefix and JWT authentication required)
    logger.debug("Registering authenticated routes with /api prefix:")

    logger.debug("Adding user router with /api prefix")
    app.include_router(user.router, prefix="/api", tags=["users"])
    logger.debug("User router added")

    logger.debug("Adding fleet router with /api prefix")
    app.include_router(fleet.router, prefix="/api", tags=["fleet"])
    logger.debug("Fleet router added")

    logger.debug("Adding config management router with /api prefix")
    app.include_router(config_management.router, prefix="/api", tags=["config"])
    logger.debug("Config management router added")

    logger.debug("Adding diagnostics router with /api prefix")
    app.include_router(diagnostics.router, prefix="/api", tags=["diagnostics"])
    logger.debug("Diagnostics router added")

    logger.debug("Adding email router with /api prefix")
    app.include_router(email.router, prefix="/api", tags=["email"])
    logger.debug("Email router added")

    logger.debug("Adding profile router with /api prefix")
    app.include_router(profile.router, prefix="/api", tags=["profile"])
    logger.debug("Profile router added")

    logger.debug("Adding user preferences router with /api/user-preferences prefix")
    app.include_router(
        user_preferences.router,
        prefix="/api/user-preferences",
        tags=["user-preferences"],
    )
    logger.debug("User preferences router added")

    logger.debug("Adding updates router with /api/updates prefix")
    app.include_router(updates.router, prefix="/api/updates", tags=["updates"])
    logger.debug("Updates router added")

    logger.debug("Adding scripts router with /api/scripts prefix")
    app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
    logger.debug("Scripts router added")

    logger.debug("Adding reports router")
    app.include_router(reports.router, tags=["reports"])
    logger.debug("Reports router added")

    logger.debug("Adding access-groups + registration-keys routers (Phase 8.1)")
    app.include_router(access_groups.groups_router)
    app.include_router(access_groups.keys_router)

    logger.debug("Adding airgap-bundles router with /api prefix")
    app.include_router(airgap_bundles.router, prefix="/api", tags=["airgap-bundles"])

    logger.debug("Adding upgrade-profiles router (Phase 8.2)")
    app.include_router(upgrade_profiles.router)

    logger.debug("Adding package-compliance router (Phase 8.3)")
    app.include_router(package_compliance.router)

    logger.debug("Adding broadcast router (Phase 8.5)")
    app.include_router(broadcast.router)

    logger.debug(
        "Adding report-branding + report-templates + dynamic-secrets routers (Phase 8.7)"
    )
    app.include_router(report_branding.router)
    app.include_router(report_templates.router)
    app.include_router(dynamic_secrets.router)

    logger.debug("Adding tag router with /api prefix")
    app.include_router(tag.router, prefix="/api", tags=["tags"])
    logger.debug("Tag router added")

    logger.debug("Adding queue router with /api/queue prefix")
    app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
    logger.debug("Queue router added")

    logger.debug("Adding Ubuntu Pro settings router with /api/ubuntu-pro prefix")
    app.include_router(
        ubuntu_pro_settings.router, prefix="/api/ubuntu-pro", tags=["ubuntu-pro"]
    )
    logger.debug("Ubuntu Pro settings router added")

    logger.debug("Adding antivirus defaults router with /api/antivirus-defaults prefix")
    app.include_router(
        antivirus_defaults.router, prefix="/api/antivirus-defaults", tags=["antivirus"]
    )
    logger.debug("Antivirus defaults router added")

    logger.debug("Adding antivirus status router with /api prefix")
    app.include_router(antivirus_status.router, prefix="/api", tags=["antivirus"])
    logger.debug("Antivirus status router added")

    logger.debug("Adding commercial antivirus status router with /api prefix")
    app.include_router(
        commercial_antivirus_status.router, prefix="/api", tags=["commercial-antivirus"]
    )
    logger.debug("Commercial antivirus status router added")

    logger.debug("Adding firewall status router with /api prefix")
    app.include_router(firewall_status.router, prefix="/api", tags=["firewall"])
    logger.debug("Firewall status router added")

    logger.debug("Adding certificates auth router with /api prefix")
    app.include_router(
        certificates.auth_router, prefix="/api", tags=["certificates"]
    )  # /api/certificates/client/* (with auth)
    logger.debug("Certificates auth router added")

    logger.debug("Adding host auth router with /api prefix")
    app.include_router(
        host.auth_router, prefix="/api", tags=["hosts"]
    )  # /api/host/* (with auth)
    logger.debug("Host auth router added")

    logger.debug("Adding host hostname router with /api prefix")
    app.include_router(
        host_hostname.router, prefix="/api", tags=["hosts"]
    )  # /api/host/{host_id}/change-hostname (with auth)
    logger.debug("Host hostname router added")

    logger.debug("Adding security router with /api prefix")
    app.include_router(
        security.router, prefix="/api", tags=["security"]
    )  # /api/security/* (with auth)
    logger.debug("Security router added")

    logger.debug("Adding password reset admin router with /api prefix")
    app.include_router(
        password_reset.admin_router, prefix="/api", tags=["password_reset"]
    )  # /api/admin/reset-user-password (with auth)
    logger.debug("Password reset admin router added")

    logger.debug("Adding packages router with /api/packages prefix")
    app.include_router(
        packages.router, prefix="/api/packages", tags=["packages"]
    )  # /api/packages/* (with auth)
    logger.debug("Packages router added")

    logger.debug("Adding OpenBAO router with /api prefix")
    app.include_router(
        openbao.router, prefix="/api", tags=["openbao"]
    )  # /api/openbao/* (with auth)
    logger.debug("OpenBAO router added")

    logger.debug("Adding secrets router with /api prefix")
    app.include_router(
        secrets.router, prefix="/api", tags=["secrets"]
    )  # /api/secrets/* (with auth)
    logger.debug("Secrets router added")

    logger.debug("Adding Grafana integration router with /api prefix")
    app.include_router(
        grafana_integration.router, prefix="/api/grafana", tags=["grafana"]
    )  # /api/grafana/* (with auth)
    logger.debug("Grafana integration router added")

    logger.debug("Adding Graylog integration router with /api prefix")
    app.include_router(
        graylog_integration.router, prefix="/api/graylog", tags=["graylog"]
    )  # /api/graylog/* (with auth)
    logger.debug("Graylog integration router added")

    logger.debug("Adding Telemetry router with /api prefix")
    app.include_router(
        telemetry.router, prefix="/api/telemetry", tags=["telemetry"]
    )  # /api/telemetry/* (with auth)
    logger.debug("Telemetry router added")

    logger.debug("Adding OpenTelemetry router with /api prefix")
    app.include_router(
        opentelemetry.router, prefix="/api/opentelemetry", tags=["opentelemetry"]
    )  # /api/opentelemetry/* (with auth)
    logger.debug("OpenTelemetry router added")

    logger.debug("Adding Security Roles router")
    app.include_router(security_roles.router)  # /api/security-roles/* (with auth)
    logger.debug("Security Roles router added")

    logger.debug("Adding Third-Party Repositories router with /api prefix")
    app.include_router(
        third_party_repos.router, prefix="/api", tags=["third-party-repos"]
    )  # /api/hosts/{host_id}/third-party-repos/* (with auth)
    logger.debug("Third-Party Repositories router added")

    logger.debug("Adding Audit Log router")
    app.include_router(audit_log.router)  # /api/audit-log/* (with auth)
    logger.debug("Audit Log router added")

    logger.debug(
        "Adding Default Repositories router with /api/default-repositories prefix"
    )
    app.include_router(
        default_repositories.router,
        prefix="/api/default-repositories",
        tags=["default-repositories"],
    )  # /api/default-repositories/* (with auth)
    logger.debug("Default Repositories router added")

    logger.debug(
        "Adding Enabled Package Managers router with /api/enabled-package-managers prefix"
    )
    app.include_router(
        enabled_package_managers.router,
        prefix="/api/enabled-package-managers",
        tags=["enabled-package-managers"],
    )  # /api/enabled-package-managers/* (with auth)
    logger.debug("Enabled Package Managers router added")

    logger.debug("Adding Firewall Roles router with /api/firewall-roles prefix")
    app.include_router(
        firewall_roles.router,
        prefix="/api/firewall-roles",
        tags=["firewall-roles"],
    )  # /api/firewall-roles/* (with auth)
    logger.debug("Firewall Roles router added")

    logger.debug("Adding Child Host router with /api prefix")
    app.include_router(
        child_host.router,
        prefix="/api",
        tags=["child-hosts"],
    )  # /api/host/{host_id}/children/*, /api/child-host-distributions/* (with auth)
    logger.debug("Child Host router added")

    logger.debug("Adding Reboot Orchestration router with /api prefix")
    app.include_router(
        reboot_orchestration.router,
        prefix="/api",
        tags=["reboot-orchestration"],
    )  # /api/host/{host_id}/reboot/* (with auth)
    logger.debug("Reboot Orchestration router added")

    logger.debug("Adding License Management router with /api prefix")
    app.include_router(
        license_management.router,
        prefix="/api",
        tags=["license-management", "pro-plus"],
    )  # /api/license/* (with auth, Pro+)
    logger.debug("License Management router added")

    # Note: Pro+ module routes are mounted in lifecycle.py after modules are loaded
    # This ensures the compiled Cython modules are available before route mounting
    logger.debug("Pro+ module routes will be mounted after modules load in lifespan")

    logger.debug("Adding Plugin Bundle router with /api prefix")
    app.include_router(
        plugin_bundle.router,
        prefix="/api",
        tags=["plugins"],
    )  # /api/plugins/* (with auth)
    logger.debug("Plugin Bundle router added")

    logger.debug("Adding CVE Refresh Settings router with /api/cve-refresh prefix")
    app.include_router(
        cve_refresh_settings.router,
        prefix="/api/cve-refresh",
        tags=["cve-refresh", "pro-plus"],
    )  # /api/cve-refresh/* (with auth)
    logger.debug("CVE Refresh Settings router added")

    logger.debug("=== ALL ROUTES REGISTERED ===")

    # Log all registered routes for debugging
    logger.debug("=== ROUTE SUMMARY ===")
    route_count = 0
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            logger.debug("Route: %s %s", list(route.methods), route.path)
            route_count += 1
        elif hasattr(route, "path"):
            logger.debug("Route: %s", route.path)
            route_count += 1
    logger.info("Total routes registered: %d", route_count)


def register_app_routes(app: FastAPI):
    """
    Register basic application routes (root, health check).

    Args:
        app: The FastAPI application instance
    """
    logger.debug("=== REGISTERING APPLICATION ROUTES ===")

    @app.get("/")
    async def root():
        """
        This function provides the HTTP response to calls to the root path of
        the service.
        """
        logger.debug("Root endpoint called")
        return {"message": "Hello World"}

    logger.debug("Root route (/) registered")

    @app.get("/api/health")
    @app.head("/api/health")
    async def health_check():
        """
        Health check endpoint for connection monitoring.
        """
        logger.debug("Health check endpoint called")
        return {"status": "healthy"}

    logger.debug("Health check routes (/api/health) registered")
    logger.debug("=== APPLICATION ROUTES REGISTRATION COMPLETE ===")
