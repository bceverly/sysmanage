"""
Route registration module for the SysManage server.

This module provides functions to register all API routes including both
authenticated and unauthenticated endpoints.
"""

from fastapi import FastAPI

from backend.api import (
    access_groups,
    advisory_actions,
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
    custom_metric_exporter,
    cve_refresh_settings,
    default_repositories,
    diagnostics,
    dynamic_secrets,
    email,
    enabled_package_managers,
    external_idp,
    federation_identity,
    fips_actions,
    firewall_roles,
    firewall_status,
    fleet,
    grafana_integration,
    graylog_integration,
    host,
    host_hostname,
    invitations,
    license_management,
    lifecycle_actions,
    logging_settings,
    maintenance_windows,
    openbao,
    opentelemetry,
    package_compliance,
    packages,
    password_reset,
    plugin_bundle,
    processes,
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

    Mounts the router once, at ``/api/v1{suffix}`` — the canonical versioned
    route.  The deprecated unversioned ``/api{suffix}`` alias was retired as the
    final Phase 13.2.1 action (the migration is complete: every feature is native
    ``/api/v1``, so the one-release back-compat window for pre-13.2.1 callers is
    closed).  The deliberately-unversioned surfaces (agent, auth/mfa, IdP
    SSO/ACS, SCIM) are registered directly, not through this helper, so they keep
    their bare ``/api`` paths.
    """
    app.include_router(router, prefix="/api/v1" + suffix, tags=tags)


def _include_renamed(
    app: FastAPI, router, *, new_prefix: str, old_prefix: str, tags=None
):
    """Register a router at its canonical ``/api/v1`` path (Phase 13.2.1).

    Option A: used where the bare feature name under ``/api/v1`` is already owned
    by a Pro+ engine (``secrets_engine`` → ``/api/v1/secrets``, ``reporting_engine``
    → ``/api/v1/reports``).  The OSS feature takes a DISTINCT v1 name
    (``/api/v1/stored-secrets``, ``/api/v1/reporting``) so the two never collide.
    ``old_prefix`` is retained in the signature for call-site clarity but the
    deprecated unversioned alias mount has been retired (bridge removal).
    """
    del old_prefix  # deprecated /api alias retired (Phase 13.2.1 bridge removal)
    app.include_router(router, prefix=new_prefix, tags=tags)


def check_route_collisions(app: FastAPI, *, strict: bool = False) -> dict:
    """Surface routes that share the same (method, path) — Phase 13.2.1.

    The ``/api/v1`` native + ``/api`` alias mounts are DIFFERENT paths, so they
    are NOT collisions.  A genuine duplicate means one endpoint silently shadows
    another (Starlette matches first-registered) — most dangerously across the
    OSS↔Pro+ boundary, where the compiled engine mounts at runtime on licensed
    boxes and neither test suite covers the seam.  This guard turns that silent
    heisenbug into a **loud** one.

    Behaviour:
      * Always logs an ERROR (with the offending ``method path -> handlers``)
        when collisions exist — so they're visible in every startup log / CI.
      * ``strict=True`` *additionally* raises ``RuntimeError`` — for tests/CI
        that want to fail fast on a NEW collision.

    It deliberately does NOT crash startup by default: there are pre-existing,
    long-tolerated duplicates among the Pro+ stub mounts (e.g. av/firewall stubs
    sharing ``/api/status/{host_id}`` and ``/api/deploy``), and a hard failure
    there would take down Community-Edition boxes over a benign first-match-wins
    condition.  Returns the collisions dict (empty when clean).

    Call this AFTER all routers are registered (including the Pro+ engine/stub
    mounts in the lifespan), so it sees the fully-assembled route table.
    """
    from collections import Counter  # noqa: PLC0415

    seen: Counter = Counter()
    owners: dict = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or {"WEBSOCKET"}
        for method in methods:
            key = (method, path)
            seen[key] += 1
            owners.setdefault(key, []).append(getattr(route, "name", "?"))

    collisions = {key: owners[key] for key, count in seen.items() if count > 1}
    if collisions:
        detail = "\n".join(
            f"  {method} {path}  ->  {names}"
            for (method, path), names in sorted(collisions.items())
        )
        msg = (
            "Route collision(s) detected — the same method+path is registered "
            "more than once, so one handler silently shadows another (commonly "
            "an OSS router and a Pro+ engine claiming the same /api/v1 path). "
            "Give them disjoint sub-paths.\n" + detail
        )
        logger.error(msg)
        if strict:
            raise RuntimeError(msg)
        return collisions
    logger.info("Route collision guard: OK (%d routes, no duplicates)", len(app.routes))
    return {}


def register_routes(app: FastAPI):
    """
    Register all API routes with the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    logger.debug("=== REGISTERING ROUTES ===")

    # Unauthenticated routes (no /api prefix)
    logger.debug("Registering unauthenticated routes:")

    logger.debug("Adding auth router (native /api/v1; bridge retired)")
    _include_versioned(
        app, auth.router, tags=["authentication"]
    )  # /api/v1/login, /refresh, /logout
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

    # Custom Metrics Prometheus exporter — UNAUTHENTICATED (Prometheus-scrape
    # convention).  Mounted at the app ROOT so the path is exactly
    # ``/metrics/custom-metrics`` (NOT under /api/v1), the way the infra/health
    # routes are.  Must be firewalled to the Prometheus host (see module
    # docstring).
    app.include_router(custom_metric_exporter.router)
    logger.debug("Custom-metric Prometheus exporter router added")

    # Phase 13.1.H — server-scoped configuration settings (Settings →
    # Configuration UI).  Phase 13.2.1: native /api/v1/settings + /api alias.
    _include_versioned(app, server_settings.router, tags=["settings"])
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

    # Phase 13.2.1 — Slice 8: native /api/v1/mirror-* (+ deprecated /api alias).
    _include_versioned(app, repository_mirroring.router, tags=["repository-mirroring"])
    logger.debug("Repository mirroring router added")

    # SSO/ACS/metadata callbacks — IdP-configured URLs, kept unversioned.
    logger.debug("Adding external IdP SSO callback router (unversioned /api/auth/*)")
    app.include_router(external_idp.router)
    # Provider/settings management — native /api/v1 + deprecated /api alias.
    logger.debug("Adding external IdP management router (native /api/v1 + alias)")
    _include_versioned(app, external_idp.mgmt_router, tags=["external-idp"])
    logger.debug("External IdP routers added")

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

    logger.debug("Adding password reset router (native /api/v1 + deprecated alias)")
    _include_versioned(
        app, password_reset.router, tags=["password-reset"]
    )  # /api/v1/forgot-password, /reset-password, /validate-reset-token (+ /api alias)
    logger.debug("Password reset router added")

    # Phase 13.3 — administrator invitations (invite by email + role; recipient
    # accepts via a tokened link that creates their account).
    logger.debug("Adding invitations router (native /api/v1 + deprecated alias)")
    _include_versioned(
        app, invitations.router, tags=["invitations"]
    )  # /api/v1/invitations/* (+ /api alias)
    logger.debug("Invitations router added")

    logger.debug("Adding logging-settings router (native /api/v1 + alias)")
    _include_versioned(app, logging_settings.router, tags=["logging-settings"])
    logger.debug("Logging-settings router added")

    logger.debug("Adding maintenance-windows router (native /api/v1)")
    _include_versioned(app, maintenance_windows.router, tags=["maintenance-windows"])
    logger.debug("Maintenance-windows router added")

    logger.debug("Adding advisory-actions router (native /api/v1)")
    _include_versioned(app, advisory_actions.router, tags=["advisories"])
    logger.debug("Advisory-actions router added")

    logger.debug("Adding lifecycle-actions router (native /api/v1)")
    _include_versioned(app, lifecycle_actions.router, tags=["os-lifecycle"])
    logger.debug("Lifecycle-actions router added")

    logger.debug("Adding fips-actions router (native /api/v1)")
    _include_versioned(app, fips_actions.router, tags=["fips-compliance"])
    logger.debug("FIPS-actions router added")

    # Secure routes (with /api prefix and JWT authentication required)
    logger.debug("Registering authenticated routes with /api prefix:")

    logger.debug("Adding user router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, user.router, tags=["users"])
    logger.debug("User router added")

    logger.debug("Adding fleet router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, fleet.router, tags=["fleet"])
    logger.debug("Fleet router added")

    logger.debug("Adding config management router (native /api/v1 + alias)")
    _include_versioned(app, config_management.router, tags=["config"])
    logger.debug("Config management router added")

    logger.debug("Adding diagnostics router (native /api/v1 + alias)")
    _include_versioned(app, diagnostics.router, tags=["diagnostics"])
    logger.debug("Diagnostics router added")

    logger.debug("Adding email router (native /api/v1 + alias)")
    _include_versioned(app, email.router, tags=["email"])
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

    # Deferred from 13.2.1: OSS `reports` stays on /api/reports — the Pro+
    # reporting_engine already owns the /api/v1/reports namespace, so moving OSS
    # there would shadow it. Needs the same namespace decision as OSS `secrets`.
    # Phase 13.2.1 (option A): OSS reports takes a distinct v1 name
    # (/api/v1/reporting) because the Pro+ reporting_engine owns /api/v1/reports
    # with the same view/generate/screenshots endpoints. /api/reports kept as a
    # deprecated alias.
    logger.debug(
        "Adding reports router (native /api/v1/reporting + /api/reports alias)"
    )
    _include_renamed(
        app,
        reports.router,
        new_prefix="/api/v1/reporting",
        old_prefix="/api/reports",
    )
    logger.debug("Reports router added")

    logger.debug(
        "Adding access-groups + registration-keys routers (native /api/v1 + alias)"
    )
    _include_versioned(app, access_groups.groups_router)
    _include_versioned(app, access_groups.keys_router)

    logger.debug("Adding airgap-bundles router (native /api/v1 + alias)")
    _include_versioned(app, airgap_bundles.router, tags=["airgap-bundles"])
    # Token-authed streaming bundle download (no blanket JWTBearer) so the
    # browser can stream multi-GB ISOs without buffering them in a Blob.
    _include_versioned(app, airgap_bundles.download_router, tags=["airgap-bundles"])

    logger.debug("Adding upgrade-profiles router (native /api/v1 + deprecated alias)")
    _include_versioned(app, upgrade_profiles.router, suffix="/upgrade-profiles")

    logger.debug("Adding package-compliance router (native /api/v1 + deprecated alias)")
    _include_versioned(app, package_compliance.router, suffix="/package-profiles")

    logger.debug("Adding broadcast router (native /api/v1 + alias)")
    _include_versioned(app, broadcast.router)

    logger.debug(
        "Adding report-branding + report-templates + dynamic-secrets routers "
        "(native /api/v1 + alias)"
    )
    _include_versioned(app, report_branding.router)
    _include_versioned(app, report_templates.router)
    _include_versioned(app, dynamic_secrets.router)

    # GPG Key Management relocated into the Pro+ secrets_engine (Pro+ moat):
    # the endpoints now live under /api/v1/secrets/gpg-keys*, served by the
    # licensed engine (or the OSS licensed-stub when the engine is absent).

    logger.debug("Adding tag router (native /api/v1 + deprecated /api alias)")
    _include_versioned(app, tag.router, tags=["tags"])
    logger.debug("Tag router added")

    logger.debug("Adding queue router (native /api/v1 + alias)")
    _include_versioned(app, queue.router, suffix="/queue", tags=["queue"])
    logger.debug("Queue router added")

    logger.debug("Adding Ubuntu Pro settings router (native /api/v1 + alias)")
    _include_versioned(
        app, ubuntu_pro_settings.router, suffix="/ubuntu-pro", tags=["ubuntu-pro"]
    )
    logger.debug("Ubuntu Pro settings router added")

    logger.debug("Adding antivirus defaults router (native /api/v1 + alias)")
    _include_versioned(
        app,
        antivirus_defaults.router,
        suffix="/antivirus-defaults",
        tags=["antivirus"],
    )
    logger.debug("Antivirus defaults router added")

    logger.debug("Adding antivirus status router (native /api/v1 + alias)")
    _include_versioned(app, antivirus_status.router, tags=["antivirus"])
    logger.debug("Antivirus status router added")

    logger.debug("Adding commercial antivirus status router (native /api/v1 + alias)")
    _include_versioned(
        app, commercial_antivirus_status.router, tags=["commercial-antivirus"]
    )
    logger.debug("Commercial antivirus status router added")

    logger.debug("Adding firewall status router (native /api/v1 + alias)")
    _include_versioned(app, firewall_status.router, tags=["firewall"])
    logger.debug("Firewall status router added")

    logger.debug("Adding processes router (native /api/v1 + alias)")
    _include_versioned(app, processes.router, tags=["processes"])
    logger.debug("Processes router added")

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

    logger.debug("Adding security router (native /api/v1 + deprecated /api alias)")
    _include_versioned(
        app, security.router, tags=["security"]
    )  # /api/v1/security/* (+ /api alias)
    logger.debug("Security router added")

    logger.debug("Adding password reset admin router (native /api/v1 + alias)")
    _include_versioned(
        app, password_reset.admin_router, tags=["password_reset"]
    )  # /api/v1/admin/reset-user-password (+ /api alias)
    logger.debug("Password reset admin router added")

    logger.debug("Adding packages router (native /api/v1 + deprecated /api alias)")
    _include_versioned(
        app, packages.router, suffix="/packages", tags=["packages"]
    )  # /api/v1/packages/* (+ /api alias)
    logger.debug("Packages router added")

    logger.debug("Adding OpenBAO router (native /api/v1 + deprecated /api alias)")
    _include_versioned(
        app, openbao.router, tags=["openbao"]
    )  # /api/v1/openbao/* (+ /api alias)
    logger.debug("OpenBAO router added")

    # Phase 13.2.1 (option A): OSS secrets takes a distinct v1 name
    # (/api/v1/stored-secrets) because the Pro+ secrets_engine owns
    # /api/v1/secrets with the same deploy-ssh-keys/deploy-certificates/types
    # endpoints. /api/secrets kept as a deprecated alias.
    logger.debug(
        "Adding secrets routers (native /api/v1/stored-secrets + /api/secrets alias)"
    )
    # Registered as ordered sub-routers (types before crud) — their collection
    # routes use a bare "" path that needs the non-empty feature prefix.
    for _secrets_sub in secrets.ordered_routers:
        _include_renamed(
            app,
            _secrets_sub,
            new_prefix="/api/v1/stored-secrets",
            old_prefix="/api/secrets",
            tags=["secrets"],
        )
    logger.debug("Secrets router added")

    logger.debug("Adding Grafana integration router (native /api/v1 + alias)")
    _include_versioned(
        app, grafana_integration.router, suffix="/grafana", tags=["grafana"]
    )  # /api/v1/grafana/* (+ /api alias)
    logger.debug("Grafana integration router added")

    logger.debug("Adding Graylog integration router (native /api/v1 + alias)")
    _include_versioned(
        app, graylog_integration.router, suffix="/graylog", tags=["graylog"]
    )  # /api/v1/graylog/* (+ /api alias)
    logger.debug("Graylog integration router added")

    logger.debug("Adding Telemetry router (native /api/v1 + alias)")
    _include_versioned(
        app, telemetry.router, suffix="/telemetry", tags=["telemetry"]
    )  # /api/v1/telemetry/* (+ /api alias)
    logger.debug("Telemetry router added")

    logger.debug("Adding OpenTelemetry router (native /api/v1 + alias)")
    _include_versioned(
        app, opentelemetry.router, suffix="/opentelemetry", tags=["opentelemetry"]
    )  # /api/v1/opentelemetry/* (+ /api alias)
    logger.debug("OpenTelemetry router added")

    logger.debug("Adding Security Roles router (native /api/v1 + deprecated alias)")
    _include_versioned(
        app, security_roles.router
    )  # /api/v1/security-roles/* (+ /api alias)
    logger.debug("Security Roles router added")

    logger.debug("Adding Third-Party Repositories router (native /api/v1 + alias)")
    _include_versioned(
        app, third_party_repos.router, tags=["third-party-repos"]
    )  # /api/v1/hosts/{host_id}/third-party-repos/* (+ /api alias)
    logger.debug("Third-Party Repositories router added")

    logger.debug("Adding Audit Log router (native /api/v1 + alias)")
    _include_versioned(app, audit_log.router)  # /api/v1/audit-log/* (+ /api alias)
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

    logger.debug("Adding Firewall Roles router (native /api/v1 + alias)")
    _include_versioned(
        app,
        firewall_roles.router,
        suffix="/firewall-roles",
        tags=["firewall-roles"],
    )  # /api/v1/firewall-roles/* (+ /api alias)
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

    logger.debug("Adding License Management router (native /api/v1 + alias)")
    _include_versioned(
        app,
        license_management.router,
        tags=["license-management", "pro-plus"],
    )  # /api/v1/license/* (+ /api alias)
    logger.debug("License Management router added")

    # Note: Pro+ module routes are mounted in lifecycle.py after modules are loaded
    # This ensures the compiled Cython modules are available before route mounting
    logger.debug("Pro+ module routes will be mounted after modules load in lifespan")

    logger.debug("Adding Plugin Bundle router (native /api/v1 + alias)")
    _include_versioned(
        app,
        plugin_bundle.router,
        tags=["plugins"],
    )  # /api/v1/plugins/* (+ /api alias)
    logger.debug("Plugin Bundle router added")

    logger.debug("Adding CVE Refresh Settings router (native /api/v1 + alias)")
    _include_versioned(
        app,
        cve_refresh_settings.router,
        suffix="/cve-refresh",
        tags=["cve-refresh", "pro-plus"],
    )  # /api/v1/cve-refresh/* (+ /api alias)
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
