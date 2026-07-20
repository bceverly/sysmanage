# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Pro+ Route Mounting - Thin Wrappers for Cython Modules

This module provides thin wrappers that mount routes from compiled
Cython modules (vuln_engine, health_engine) when available.

The actual route implementations, service logic, and business rules
are all contained within the compiled modules.
"""

from fastapi import Depends, FastAPI, HTTPException, status

from backend.auth.auth_bearer import get_current_user
from backend.licensing.license_service import (  # pylint: disable=unused-import
    license_service,
)
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.services.email_service import email_service
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.proplus_routes")

# Shared dependency-gate factories + the Cython compat shim live in a sibling
# module; re-imported here so ``proplus_routes._feature_dependency`` /
# ``_module_dependency`` / ``_cython_compat`` (referenced by tests and by the
# mount functions below) remain importable from this module.
from backend.api.proplus_routes_common import (  # noqa: E402  pylint: disable=unused-import
    _cython_compat,
    _feature_dependency,
    _module_dependency,
)

# The remaining per-engine mount functions + the licensed-stub route groups live
# in sibling modules (extracted to keep every file under the line-count cap).
# Re-imported here so ``mount_proplus_routes`` can call them and so every
# ``mount_*_routes`` name (and ``mount_proplus_stub_routes``) stays importable
# from ``proplus_routes`` exactly as before.
from backend.api.proplus_routes_mounts import (  # noqa: E402  pylint: disable=unused-import
    mount_audit_routes,
    mount_automation_routes,
    mount_av_management_routes,
    mount_container_routes,
    mount_firewall_orchestration_routes,
    mount_fleet_routes,
    mount_multitenancy_routes,
    mount_observability_routes,
    mount_secrets_routes,
    mount_virtualization_routes,
)
from backend.api.proplus_routes_stubs import (  # noqa: E402  pylint: disable=unused-import
    mount_proplus_stub_routes,
)


def mount_vulnerability_routes(app: FastAPI) -> bool:
    """
    Mount vulnerability routes from the vuln_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    vuln_engine = module_loader.get_module("vuln_engine")
    if vuln_engine is None:
        logger.debug("vuln_engine module not loaded, skipping vulnerability routes")
        return False

    # Check if module provides routes
    module_info = vuln_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("vuln_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = vuln_engine.get_vulnerability_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted vulnerability routes from vuln_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount vulnerability routes: %s", e)
        return False


def mount_advisory_routes(app: FastAPI) -> bool:
    """
    Mount advisory/errata routes from the advisory_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    advisory_engine = module_loader.get_module("advisory_engine")
    if advisory_engine is None:
        logger.debug("advisory_engine module not loaded, skipping advisory routes")
        return False

    module_info = advisory_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("advisory_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = advisory_engine.get_advisory_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted advisory routes from advisory_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount advisory routes: %s", e)
        return False


def mount_lifecycle_routes(app: FastAPI) -> bool:
    """
    Mount OS-lifecycle / release-upgrade routes from the lifecycle_engine
    module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    lifecycle_engine = module_loader.get_module("lifecycle_engine")
    if lifecycle_engine is None:
        logger.debug("lifecycle_engine module not loaded, skipping lifecycle routes")
        return False

    module_info = lifecycle_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("lifecycle_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = lifecycle_engine.get_lifecycle_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted OS-lifecycle routes from lifecycle_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount OS-lifecycle routes: %s", e)
        return False


def mount_health_routes(app: FastAPI) -> bool:
    """
    Mount health analysis routes from the health_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    health_engine = module_loader.get_module("health_engine")
    if health_engine is None:
        logger.debug("health_engine module not loaded, skipping health routes")
        return False

    # Check if module provides routes
    module_info = health_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("health_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = health_engine.get_health_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted health routes from health_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount health routes: %s", e)
        return False


def mount_compliance_routes(app: FastAPI) -> bool:
    """
    Mount compliance routes from the compliance_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    compliance_engine = module_loader.get_module("compliance_engine")
    if compliance_engine is None:
        logger.debug("compliance_engine module not loaded, skipping compliance routes")
        return False

    # Check if module provides routes
    module_info = compliance_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("compliance_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = compliance_engine.get_compliance_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted compliance routes from compliance_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount compliance routes: %s", e)
        return False


def mount_alerting_routes(app: FastAPI) -> bool:
    """
    Mount alerting routes from the alerting_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    alerting_engine = module_loader.get_module("alerting_engine")
    if alerting_engine is None:
        logger.debug("alerting_engine module not loaded, skipping alerting routes")
        return False

    # Check if module provides routes
    module_info = alerting_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("alerting_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = alerting_engine.get_alerting_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
                email_service=email_service,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted alerting routes from alerting_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount alerting routes: %s", e)
        return False


def mount_reporting_routes(app: FastAPI) -> bool:
    """
    Mount reporting routes from the reporting_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    reporting_engine = module_loader.get_module("reporting_engine")
    if reporting_engine is None:
        logger.debug("reporting_engine module not loaded, skipping reporting routes")
        return False

    # Check if module provides routes
    module_info = reporting_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("reporting_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = reporting_engine.get_reporting_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted reporting routes from reporting_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount reporting routes: %s", e)
        return False


def _federation_role() -> str:
    """This server's configured federation role (``none`` on any failure).

    Read from the ``server_configuration`` DB singleton so the role chosen
    in Settings → Server Role actually gates which federation engine is
    active.  Late import keeps route-registration import-time free of a DB
    dependency; degrades to ``none`` (mount nothing) if the DB isn't ready.
    """
    try:
        from backend.services.server_config_service import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            get_federation_role,
        )

        return get_federation_role()
    except Exception:  # pylint: disable=broad-exception-caught
        return "none"


def mount_federation_site_routes(app: FastAPI) -> bool:
    """Mount site-side federation routes from federation_site_engine.

    The site engine handles the inbound side of the federation
    protocol — endpoints the coordinator calls to enroll, push
    policies, and dispatch commands — plus an outbound sync worker
    that drains ``federation_sync_queue`` upstream.  When loaded,
    its router replaces the OSS stubs under ``/api/v1/federation/site/*``.

    Coordinator and site engines are mutually exclusive in practice
    (a server runs as one role or the other), but both mount-paths
    are tested independently so a misconfigured deployment that
    loads both engines doesn't surprise the operator.
    """
    site_engine = module_loader.get_module("federation_site_engine")
    if site_engine is None:
        logger.debug(
            "federation_site_engine module not loaded, "
            "skipping federation site routes"
        )
        return False

    module_info = site_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("federation_site_engine module does not provide routes")
        return False

    role = _federation_role()
    if role != "site":
        logger.info(
            "federation_site_engine is loaded but this server's federation role "
            "is %r, not 'site'; serving the OSS stubs instead.",
            role,
        )
        return False

    try:
        with _cython_compat():
            router = site_engine.get_federation_site_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted federation site routes from federation_site_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to mount federation site routes: %s", exc)
        return False


def mount_federation_controller_routes(app: FastAPI) -> bool:
    """Mount federation coordinator routes from federation_controller_engine.

    Returns True if the engine was loaded and its routes were mounted,
    False otherwise.  The Cython engine (lives in the Pro+ source repo,
    NOT this OSS one) exposes ``get_federation_controller_router(...)``
    with the same dependency-injection signature as every other Pro+
    engine — keeping the wiring uniform.
    """
    federation_engine = module_loader.get_module("federation_controller_engine")
    if federation_engine is None:
        logger.debug(
            "federation_controller_engine module not loaded, "
            "skipping federation controller routes"
        )
        return False

    module_info = federation_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("federation_controller_engine module does not provide routes")
        return False

    role = _federation_role()
    if role != "coordinator":
        logger.info(
            "federation_controller_engine is loaded but this server's federation "
            "role is %r, not 'coordinator'; serving the OSS stubs instead.",
            role,
        )
        return False

    try:
        with _cython_compat():
            router = federation_engine.get_federation_controller_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted federation controller routes from "
            "federation_controller_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to mount federation controller routes: %s", exc)
        return False


def mount_proplus_routes(app: FastAPI) -> dict:
    """
    Mount all Pro+ module routes if modules are available.

    This is the main entry point called during app startup to
    mount routes from all available Cython modules.

    Args:
        app: The FastAPI application instance

    Returns:
        Dictionary with mount status for each module
    """
    results = {
        "vuln_engine": mount_vulnerability_routes(app),
        "advisory_engine": mount_advisory_routes(app),
        "lifecycle_engine": mount_lifecycle_routes(app),
        "health_engine": mount_health_routes(app),
        "compliance_engine": mount_compliance_routes(app),
        "alerting_engine": mount_alerting_routes(app),
        "reporting_engine": mount_reporting_routes(app),
        "audit_engine": mount_audit_routes(app),
        "secrets_engine": mount_secrets_routes(app),
        "container_engine": mount_container_routes(app),
        "av_management_engine": mount_av_management_routes(app),
        "firewall_orchestration_engine": mount_firewall_orchestration_routes(app),
        "automation_engine": mount_automation_routes(app),
        "fleet_engine": mount_fleet_routes(app),
        "virtualization_engine": mount_virtualization_routes(app),
        "observability_engine": mount_observability_routes(app),
        "federation_controller_engine": mount_federation_controller_routes(app),
        "federation_site_engine": mount_federation_site_routes(app),
        "multitenancy_engine": mount_multitenancy_routes(app),
    }

    mounted_count = sum(1 for v in results.values() if v)
    if mounted_count > 0:
        logger.info("Mounted %d Pro+ module route(s)", mounted_count)
    else:
        logger.debug("No Pro+ module routes mounted")

    # Mount stub routes for any modules that weren't loaded
    mount_proplus_stub_routes(app, results)

    return results
