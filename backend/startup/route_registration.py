"""
Route registration module for the SysManage server.

This module provides functions to register all API routes including both
authenticated and unauthenticated endpoints.
"""

from fastapi import FastAPI

from backend.api import (
    agent,
    antivirus_defaults,
    antivirus_status,
    auth,
    certificates,
    config_management,
    diagnostics,
    email,
    fleet,
    grafana_integration,
    host,
    openbao,
    opentelemetry,
    packages,
    password_reset,
    profile,
    queue,
    reports,
    scripts,
    secrets,
    security,
    security_roles,
    tag,
    telemetry,
    third_party_repos,
    ubuntu_pro_settings,
    updates,
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
    logger.info("=== REGISTERING ROUTES ===")

    # Unauthenticated routes (no /api prefix)
    logger.info("Registering unauthenticated routes:")

    logger.info("Adding auth router (no prefix)")
    app.include_router(auth.router)  # /login, /refresh
    logger.info("Auth router added")

    logger.info("Adding agent public router (no prefix)")
    app.include_router(agent.public_router)  # /agent/auth (no auth required)
    logger.info("Agent public router added")

    logger.info("Adding agent authenticated router with /api prefix")
    app.include_router(
        agent.router, prefix="/api"
    )  # /api/agent/connect, /api/agent/installation-complete
    logger.info("Agent authenticated router added")

    logger.info("Adding host public router (no prefix)")
    app.include_router(host.public_router)  # /host/register (no auth)
    logger.info("Host public router added")

    logger.info("Adding certificates public router (no prefix)")
    app.include_router(
        certificates.public_router
    )  # /certificates/server-fingerprint, /certificates/ca-certificate (no auth)
    logger.info("Certificates public router added")

    logger.info("Adding password reset router (no prefix)")
    app.include_router(
        password_reset.router
    )  # /forgot-password, /reset-password, /validate-reset-token (no auth)
    logger.info("Password reset router added")

    # Secure routes (with /api prefix and JWT authentication required)
    logger.info("Registering authenticated routes with /api prefix:")

    logger.info("Adding user router with /api prefix")
    app.include_router(user.router, prefix="/api", tags=["users"])
    logger.info("User router added")

    logger.info("Adding fleet router with /api prefix")
    app.include_router(fleet.router, prefix="/api", tags=["fleet"])
    logger.info("Fleet router added")

    logger.info("Adding config management router with /api prefix")
    app.include_router(config_management.router, prefix="/api", tags=["config"])
    logger.info("Config management router added")

    logger.info("Adding diagnostics router with /api prefix")
    app.include_router(diagnostics.router, prefix="/api", tags=["diagnostics"])
    logger.info("Diagnostics router added")

    logger.info("Adding email router with /api prefix")
    app.include_router(email.router, prefix="/api", tags=["email"])
    logger.info("Email router added")

    logger.info("Adding profile router with /api prefix")
    app.include_router(profile.router, prefix="/api", tags=["profile"])
    logger.info("Profile router added")

    logger.info("Adding user preferences router with /api/user-preferences prefix")
    app.include_router(
        user_preferences.router,
        prefix="/api/user-preferences",
        tags=["user-preferences"],
    )
    logger.info("User preferences router added")

    logger.info("Adding updates router with /api/updates prefix")
    app.include_router(updates.router, prefix="/api/updates", tags=["updates"])
    logger.info("Updates router added")

    logger.info("Adding scripts router with /api/scripts prefix")
    app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
    logger.info("Scripts router added")

    logger.info("Adding reports router")
    app.include_router(reports.router, tags=["reports"])
    logger.info("Reports router added")

    logger.info("Adding tag router with /api prefix")
    app.include_router(tag.router, prefix="/api", tags=["tags"])
    logger.info("Tag router added")

    logger.info("Adding queue router with /api/queue prefix")
    app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
    logger.info("Queue router added")

    logger.info("Adding Ubuntu Pro settings router with /api/ubuntu-pro prefix")
    app.include_router(
        ubuntu_pro_settings.router, prefix="/api/ubuntu-pro", tags=["ubuntu-pro"]
    )
    logger.info("Ubuntu Pro settings router added")

    logger.info("Adding antivirus defaults router with /api/antivirus-defaults prefix")
    app.include_router(
        antivirus_defaults.router, prefix="/api/antivirus-defaults", tags=["antivirus"]
    )
    logger.info("Antivirus defaults router added")

    logger.info("Adding antivirus status router with /api prefix")
    app.include_router(antivirus_status.router, prefix="/api", tags=["antivirus"])
    logger.info("Antivirus status router added")

    logger.info("Adding certificates auth router with /api prefix")
    app.include_router(
        certificates.auth_router, prefix="/api", tags=["certificates"]
    )  # /api/certificates/client/* (with auth)
    logger.info("Certificates auth router added")

    logger.info("Adding host auth router with /api prefix")
    app.include_router(
        host.auth_router, prefix="/api", tags=["hosts"]
    )  # /api/host/* (with auth)
    logger.info("Host auth router added")

    logger.info("Adding security router with /api prefix")
    app.include_router(
        security.router, prefix="/api", tags=["security"]
    )  # /api/security/* (with auth)
    logger.info("Security router added")

    logger.info("Adding password reset admin router with /api prefix")
    app.include_router(
        password_reset.admin_router, prefix="/api", tags=["password_reset"]
    )  # /api/admin/reset-user-password (with auth)
    logger.info("Password reset admin router added")

    logger.info("Adding packages router with /api/packages prefix")
    app.include_router(
        packages.router, prefix="/api/packages", tags=["packages"]
    )  # /api/packages/* (with auth)
    logger.info("Packages router added")

    logger.info("Adding OpenBAO router with /api prefix")
    app.include_router(
        openbao.router, prefix="/api", tags=["openbao"]
    )  # /api/openbao/* (with auth)
    logger.info("OpenBAO router added")

    logger.info("Adding secrets router with /api prefix")
    app.include_router(
        secrets.router, prefix="/api", tags=["secrets"]
    )  # /api/secrets/* (with auth)
    logger.info("Secrets router added")

    logger.info("Adding Grafana integration router with /api prefix")
    app.include_router(
        grafana_integration.router, prefix="/api/grafana", tags=["grafana"]
    )  # /api/grafana/* (with auth)
    logger.info("Grafana integration router added")

    logger.info("Adding Telemetry router with /api prefix")
    app.include_router(
        telemetry.router, prefix="/api/telemetry", tags=["telemetry"]
    )  # /api/telemetry/* (with auth)
    logger.info("Telemetry router added")

    logger.info("Adding OpenTelemetry router with /api prefix")
    app.include_router(
        opentelemetry.router, prefix="/api/opentelemetry", tags=["opentelemetry"]
    )  # /api/opentelemetry/* (with auth)
    logger.info("OpenTelemetry router added")

    logger.info("Adding Security Roles router")
    app.include_router(security_roles.router)  # /api/security-roles/* (with auth)
    logger.info("Security Roles router added")

    logger.info("Adding Third-Party Repositories router with /api prefix")
    app.include_router(
        third_party_repos.router, prefix="/api", tags=["third-party-repos"]
    )  # /api/hosts/{host_id}/third-party-repos/* (with auth)
    logger.info("Third-Party Repositories router added")

    logger.info("=== ALL ROUTES REGISTERED ===")

    # Log all registered routes for debugging
    logger.info("=== ROUTE SUMMARY ===")
    route_count = 0
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            logger.info("Route: %s %s", list(route.methods), route.path)
            route_count += 1
        elif hasattr(route, "path"):
            logger.info("Route: %s", route.path)
            route_count += 1
    logger.info("Total routes registered: %d", route_count)


def register_app_routes(app: FastAPI):
    """
    Register basic application routes (root, health check).

    Args:
        app: The FastAPI application instance
    """
    logger.info("=== REGISTERING APPLICATION ROUTES ===")

    @app.get("/")
    async def root():
        """
        This function provides the HTTP response to calls to the root path of
        the service.
        """
        logger.debug("Root endpoint called")
        return {"message": "Hello World"}

    logger.info("Root route (/) registered")

    @app.get("/api/health")
    @app.head("/api/health")
    async def health_check():
        """
        Health check endpoint for connection monitoring.
        """
        logger.debug("Health check endpoint called")
        return {"status": "healthy"}

    logger.info("Health check routes (/api/health) registered")
    logger.info("=== APPLICATION ROUTES REGISTRATION COMPLETE ===")
