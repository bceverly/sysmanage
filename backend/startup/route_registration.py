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
    airgap_devices,
    airgap_keys,
    airgap_repository_buckets,
    airgap_repository_list,
    antivirus_defaults,
    antivirus_status,
    api_keys,
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
    federation_identity,
    firewall_roles,
    firewall_status,
    fleet,
    grafana_integration,
    graylog_integration,
    host,
    host_hostname,
    license_management,
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
    scim,
    scripts,
    secrets,
    security,
    security_roles,
    server_info,
    server_settings,
    tag,
    telemetry,
    third_party_repos,
    ubuntu_pro_settings,
    updates,
    upgrade_profiles,
    user,
    user_preferences,
)
from backend.config import config as config_module
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.startup.routes")


def _include_versioned(app: FastAPI, router, *, suffix: str = "", tags=None):
    """Register a router natively under ``/api/v1`` (Phase 13.2.1 migration).

    Mounts the router twice:

    * ``/api/v1{suffix}`` — the **canonical** versioned route (shown in OpenAPI).
      ``ApiVersionMiddleware`` matches this natively and passes it through, so the
      feature no longer depends on the v1→legacy bridge.
    * ``/api{suffix}`` — a **deprecated** unversioned alias kept for one release
      for any pre-13.2.1 external caller (e.g. API-key automation). Hidden from
      the OpenAPI schema so the docs advertise only the versioned surface.

    Drop the alias (the second mount) once the deprecation window closes.
    """
    app.include_router(router, prefix="/api/v1" + suffix, tags=tags)
    app.include_router(
        router, prefix="/api" + suffix, tags=tags, include_in_schema=False
    )


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
        auth.router, prefix="/api", tags=["authentication"]
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

    # Phase 13.1.H — server-scoped configuration settings (Settings →
    # Configuration UI).  Endpoints carry their own /api/settings prefix.
    app.include_router(server_settings.router)
    logger.debug("Server-settings router added")

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
    # Token-authed streaming ISO download lives on a separate router
    # (no blanket Authorization-header dependency) so the browser can
    # download multi-GB bundles natively via a short-lived URL token.
    app.include_router(airgap_collector_runs.download_router)
    logger.debug("Air-gap collector runs router added")

    # Phase 11 B5 — host-scoped compliance bucket endpoint that feeds
    # the AirgapComplianceBucketsCard frontend component.
    app.include_router(airgap_repository_buckets.router)
    logger.debug("Air-gap repository buckets router added")

    # Phase 11 B6 — list-all-repos + freshness endpoints feeding the
    # AirgapRepositories dashboard and RepositoryFreshnessCard.
    app.include_router(airgap_repository_list.router)
    logger.debug("Air-gap repository list router added")

    # Collector public-key display + repository trusted-key import,
    # wired into Settings → Server Role.
    app.include_router(airgap_keys.router)
    logger.debug("Air-gap keys router added")

    # Federation identity public-key display + trusted-peer import,
    # wired into the federation card on Settings → Server Role.
    app.include_router(federation_identity.router)
    # Unauthenticated public-cert endpoint (a peer fetches it to pin our cert).
    app.include_router(federation_identity.public_router)
    logger.debug("Federation identity router added")

    # Block-device enumeration + device-based ISO import (repository).
    app.include_router(airgap_devices.router)
    logger.debug("Air-gap devices router added")

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

    app.include_router(scim.router)
    logger.debug("SCIM provisioning router added")

    logger.debug("Adding agent public router with /api prefix")
    app.include_router(
        agent.public_router, prefix="/api", tags=["agent"]
    )  # /api/agent/auth (no auth required)
    logger.debug("Agent public router added")

    logger.debug("Adding agent authenticated router with /api prefix")
    app.include_router(
        agent.router, prefix="/api", tags=["agent"]
    )  # /api/agent/connect, /api/agent/installation-complete
    logger.debug("Agent authenticated router added")

    logger.debug("Adding host public router with /api prefix")
    app.include_router(
        host.public_router, prefix="/api", tags=["hosts"]
    )  # /api/host/register (no auth)
    logger.debug("Host public router added")

    logger.debug("Adding certificates public router with /api prefix")
    app.include_router(
        certificates.public_router, prefix="/api", tags=["certificates"]
    )  # /api/certificates/server-fingerprint, /api/certificates/ca-certificate (no auth)
    logger.debug("Certificates public router added")

    logger.debug("Adding password reset router with /api prefix")
    app.include_router(
        password_reset.router, prefix="/api", tags=["password-reset"]
    )  # /api/forgot-password, /api/reset-password, /api/validate-reset-token (no auth)
    logger.debug("Password reset router added")

    # Secure routes (with /api prefix and JWT authentication required)
    logger.debug("Registering authenticated routes with /api prefix:")

    logger.debug("Adding user router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, user.router, tags=["users"])
    logger.debug("User router added")

    logger.debug("Adding fleet router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, fleet.router, tags=["fleet"])
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

    logger.debug("Adding profile router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, profile.router, tags=["profile"])
    logger.debug("Profile router added")

    logger.debug("Adding user preferences router (native /api/v1 + deprecated alias)")
    _include_versioned(
        app,
        user_preferences.router,
        suffix="/user-preferences",
        tags=["user-preferences"],
    )
    logger.debug("User preferences router added")

    logger.debug("Adding updates router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, updates.router, suffix="/updates", tags=["updates"])
    logger.debug("Updates router added")

    logger.debug("Adding scripts router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, scripts.router, suffix="/scripts", tags=["scripts"])
    logger.debug("Scripts router added")

    # api-keys shipped in 13.2 with no external consumers yet, so it goes
    # straight to native /api/v1 with no deprecated /api alias (Phase 13.2.1).
    logger.debug("Adding api-keys router with /api/v1/api-keys prefix")
    app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["api-keys"])
    logger.debug("API-keys router added")

    logger.debug("Adding reports router")
    app.include_router(reports.router, tags=["reports"])
    logger.debug("Reports router added")

    logger.debug("Adding access-groups + registration-keys routers (Phase 8.1)")
    app.include_router(access_groups.groups_router)
    app.include_router(access_groups.keys_router)

    logger.debug("Adding airgap-bundles router with /api prefix")
    app.include_router(airgap_bundles.router, prefix="/api", tags=["airgap-bundles"])
    # Token-authed streaming bundle download (no blanket JWTBearer) so the
    # browser can stream multi-GB ISOs without buffering them in a Blob.
    app.include_router(
        airgap_bundles.download_router, prefix="/api", tags=["airgap-bundles"]
    )

    logger.debug("Adding upgrade-profiles router (native /api/v1 + deprecated alias)")
    _include_versioned(app, upgrade_profiles.router, suffix="/upgrade-profiles")

    logger.debug("Adding package-compliance router (native /api/v1 + deprecated alias)")
    _include_versioned(app, package_compliance.router, suffix="/package-profiles")

    logger.debug("Adding broadcast router (Phase 8.5)")
    app.include_router(broadcast.router)

    logger.debug(
        "Adding report-branding + report-templates + dynamic-secrets routers (Phase 8.7)"
    )
    app.include_router(report_branding.router)
    app.include_router(report_templates.router)
    app.include_router(dynamic_secrets.router)

    logger.debug("Adding tag router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, tag.router, tags=["tags"])
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

    # NOTE: only the AUTH router migrates. host.public_router (/host/register)
    # is agent-facing and stays unversioned (Phase 13.2.1 — fleet version skew).
    logger.debug("Adding host auth router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, host.auth_router, tags=["hosts"])
    logger.debug("Host auth router added")

    logger.debug("Adding host hostname router (native /api/v1 + deprecated alias)")
    _include_versioned(app, host_hostname.router, tags=["hosts"])
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

    logger.debug("Adding packages router (native /api/v1 + deprecated /api alias)")
    _include_versioned(
        app, packages.router, suffix="/packages", tags=["packages"]
    )  # /api/v1/packages/* (+ /api alias)
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

    logger.debug("Adding Third-Party Repositories router (native /api/v1 + alias)")
    _include_versioned(
        app, third_party_repos.router, tags=["third-party-repos"]
    )  # /api/v1/hosts/{host_id}/third-party-repos/* (+ /api alias)
    logger.debug("Third-Party Repositories router added")

    logger.debug("Adding Audit Log router")
    app.include_router(audit_log.router)  # /api/audit-log/* (with auth)
    logger.debug("Audit Log router added")

    logger.debug(
        "Adding Default Repositories router with /api/default-repositories prefix"
    )
    _include_versioned(
        app,
        default_repositories.router,
        suffix="/default-repositories",
        tags=["default-repositories"],
    )  # /api/v1/default-repositories/* (+ /api alias)
    logger.debug("Default Repositories router added")

    logger.debug(
        "Adding Enabled Package Managers router with /api/enabled-package-managers prefix"
    )
    _include_versioned(
        app,
        enabled_package_managers.router,
        suffix="/enabled-package-managers",
        tags=["enabled-package-managers"],
    )  # /api/v1/enabled-package-managers/* (+ /api alias)
    logger.debug("Enabled Package Managers router added")

    logger.debug("Adding Firewall Roles router with /api/firewall-roles prefix")
    app.include_router(
        firewall_roles.router,
        prefix="/api/firewall-roles",
        tags=["firewall-roles"],
    )  # /api/firewall-roles/* (with auth)
    logger.debug("Firewall Roles router added")

    logger.debug("Adding Child Host router (native /api/v1 + deprecated /api alias)")
    _include_versioned(
        app, child_host.router, tags=["child-hosts"]
    )  # /host/{host_id}/children/*, /child-host-distributions/* (with auth)
    logger.debug("Child Host router added")

    logger.debug("Adding Reboot Orchestration router (native /api/v1 + alias)")
    _include_versioned(
        app, reboot_orchestration.router, tags=["reboot-orchestration"]
    )  # /host/{host_id}/reboot/* (with auth)
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

    # NOTE: the multi-tenancy control-plane router is NOT mounted here.  It is
    # mounted at startup by ``mount_multitenancy_routes`` in
    # ``backend/api/proplus_routes.py`` (Pro+ relocation, Phase 2) — after the
    # licensed ``multitenancy_engine`` has loaded and been bridged into the seam,
    # so the engine's router (when present) serves the control plane, with the
    # built-in OSS router as the fallback.  Mounting here (import time) would be
    # too early to ever pick up the engine.

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
