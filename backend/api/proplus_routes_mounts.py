# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Per-engine Pro+ route-mounting functions (part B).

Extracted from ``backend.api.proplus_routes`` to keep every module under the
line-count cap.  Each ``mount_*_routes`` here follows the identical pattern as
those that remain in ``proplus_routes`` — gate on the loaded Cython engine, wrap
with ``_cython_compat()``, and ``app.include_router(...)``.  The shared gate
factories and compat shim live in ``proplus_routes_common``.  ``proplus_routes``
re-imports these so its public surface (and test references) are unchanged.
"""

from fastapi import Depends, FastAPI, HTTPException, status

from backend.api.proplus_routes_common import (
    _cython_compat,
    _feature_dependency,
    _module_dependency,
    logger,
)
from backend.auth.auth_bearer import get_current_user
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db, get_session_local


def mount_audit_routes(app: FastAPI) -> bool:
    """
    Mount audit routes from the audit_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    audit_engine = module_loader.get_module("audit_engine")
    if audit_engine is None:
        logger.debug("audit_engine module not loaded, skipping audit routes")
        return False

    # Check if module provides routes
    module_info = audit_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("audit_engine module does not provide routes")
        return False

    try:
        # audit_engine v1.1.0 has Cython cdef typed variables (cdef int,
        # cdef str) that require exact types from Query().  The
        # _cython_compat() shim returns plain int/str to satisfy those
        # checks.  Dependencies must be pre-wrapped with Depends() since
        # the module does NOT wrap them internally.
        with _cython_compat():
            router = audit_engine.get_audit_router(
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
            "Mounted audit routes from audit_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount audit routes: %s", e)
        return False


def mount_secrets_routes(app: FastAPI) -> bool:
    """
    Mount secrets routes from the secrets_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    secrets_engine = module_loader.get_module("secrets_engine")
    if secrets_engine is None:
        logger.debug("secrets_engine module not loaded, skipping secrets routes")
        return False

    # Check if module provides routes
    module_info = secrets_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("secrets_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = secrets_engine.get_secrets_router(
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
        logger.info(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            "Mounted secrets routes from secrets_engine v%s",
            str(module_info.get("version", "unknown"))[:20],
        )
        return True

    except Exception as e:
        logger.exception(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            "Failed to mount secrets routes (%s)", type(e).__name__
        )
        return False


def mount_container_routes(app: FastAPI) -> bool:
    """
    Mount container routes from the container_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    container_engine = module_loader.get_module("container_engine")
    if container_engine is None:
        logger.debug("container_engine module not loaded, skipping container routes")
        return False

    # Check if module provides routes
    module_info = container_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("container_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = container_engine.get_container_router(
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
            "Mounted container routes from container_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount container routes: %s", e)
        return False


def mount_av_management_routes(app: FastAPI) -> bool:
    """
    Mount AV management routes from the av_management_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    av_management_engine = module_loader.get_module("av_management_engine")
    if av_management_engine is None:
        logger.debug(
            "av_management_engine module not loaded, skipping AV management routes"
        )
        return False

    module_info = av_management_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("av_management_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = av_management_engine.get_av_management_router(
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
            "Mounted AV management routes from av_management_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount AV management routes: %s", e)
        return False


def mount_firewall_orchestration_routes(app: FastAPI) -> bool:
    """
    Mount firewall orchestration routes from the firewall_orchestration_engine
    module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    firewall_orchestration_engine = module_loader.get_module(
        "firewall_orchestration_engine"
    )
    if firewall_orchestration_engine is None:
        logger.debug(
            "firewall_orchestration_engine module not loaded, "
            "skipping firewall orchestration routes"
        )
        return False

    module_info = firewall_orchestration_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("firewall_orchestration_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = firewall_orchestration_engine.get_firewall_orchestration_router(
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
            "Mounted firewall orchestration routes from "
            "firewall_orchestration_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount firewall orchestration routes: %s", e)
        return False


def mount_automation_routes(app: FastAPI) -> bool:
    """
    Mount automation routes from the automation_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    automation_engine = module_loader.get_module("automation_engine")
    if automation_engine is None:
        logger.debug("automation_engine module not loaded, skipping automation routes")
        return False

    module_info = automation_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("automation_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = automation_engine.get_automation_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
                audit_log_fn=_make_automation_audit_log_fn(),
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted automation routes from automation_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount automation routes: %s", e)
        return False


def _make_automation_audit_log_fn():
    """Return a callable the automation engine invokes for each mutating endpoint."""
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    _ACTION_MAP = {
        "create": ActionType.CREATE,
        "update": ActionType.UPDATE,
        "delete": ActionType.DELETE,
        "execute": ActionType.EXECUTE,
        "approve": ActionType.PERMISSION_CHANGE,
        "reject": ActionType.PERMISSION_CHANGE,
    }

    def _log(action, entity_id, entity_name, description, current_user):
        # Pull a session lazily so the engine doesn't need to know about db.
        session_local = get_session_local()
        with session_local() as session:
            try:
                AuditService.log(
                    db=session,
                    action_type=_ACTION_MAP.get(action, ActionType.EXECUTE),
                    entity_type=EntityType.SCRIPT,
                    description=description,
                    result=Result.SUCCESS,
                    username=current_user,
                    entity_id=entity_id,
                    entity_name=entity_name,
                )
                session.commit()
            except Exception as exc:
                logger.warning("Automation audit log failed: %s", exc)
                session.rollback()

    return _log


def _make_fleet_audit_log_fn():
    """Return a callable the fleet engine invokes for each mutating endpoint."""
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    _ACTION_MAP = {
        "create": ActionType.CREATE,
        "update": ActionType.UPDATE,
        "delete": ActionType.DELETE,
        "execute": ActionType.EXECUTE,
    }

    def _log(action, entity_id, entity_name, description, current_user):
        session_local = get_session_local()
        with session_local() as session:
            try:
                AuditService.log(
                    db=session,
                    action_type=_ACTION_MAP.get(action, ActionType.EXECUTE),
                    entity_type=EntityType.HOST,
                    description=description,
                    result=Result.SUCCESS,
                    username=current_user,
                    entity_id=entity_id,
                    entity_name=entity_name,
                )
                session.commit()
            except Exception as exc:
                logger.warning("Fleet audit log failed: %s", exc)
                session.rollback()

    return _log


def mount_fleet_routes(app: FastAPI) -> bool:
    """
    Mount fleet routes from the fleet_engine module if available.

    Args:
        app: The FastAPI application instance

    Returns:
        True if routes were mounted, False otherwise
    """
    fleet_engine = module_loader.get_module("fleet_engine")
    if fleet_engine is None:
        logger.debug("fleet_engine module not loaded, skipping fleet routes")
        return False

    module_info = fleet_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("fleet_engine module does not provide routes")
        return False

    try:
        with _cython_compat():
            router = fleet_engine.get_fleet_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
                audit_log_fn=_make_fleet_audit_log_fn(),
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted fleet routes from fleet_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True

    except Exception as e:
        logger.exception("Failed to mount fleet routes: %s", e)
        return False


def _make_virtualization_audit_log_fn():
    """Audit-log adapter for the virtualization engine."""
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    def _log(action, entity_id, entity_name, description, current_user):
        session_local = get_session_local()
        with session_local() as session:
            try:
                AuditService.log(
                    db=session,
                    action_type=ActionType.EXECUTE,
                    entity_type=EntityType.HOST,
                    description=description,
                    result=Result.SUCCESS,
                    username=current_user,
                    entity_id=entity_id,
                    entity_name=entity_name,
                )
                session.commit()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Virtualization audit log failed: %s", exc)
                session.rollback()

    return _log


def mount_virtualization_routes(app: FastAPI) -> bool:
    """Mount virtualization routes from virtualization_engine if available."""
    virtualization_engine = module_loader.get_module("virtualization_engine")
    if virtualization_engine is None:
        logger.debug(
            "virtualization_engine module not loaded, skipping virtualization routes"
        )
        return False

    module_info = virtualization_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("virtualization_engine module does not provide routes")
        return False

    from backend.services.proplus_dispatch import enqueue_apply_plan

    try:
        with _cython_compat():
            router = virtualization_engine.get_virtualization_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
                dispatch_plan_fn=enqueue_apply_plan,
                audit_log_fn=_make_virtualization_audit_log_fn(),
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted virtualization routes from virtualization_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to mount virtualization routes: %s", exc)
        return False


def _make_observability_audit_log_fn():
    """Audit-log adapter for the observability engine."""
    from backend.services.audit_service import (
        ActionType,
        AuditService,
        EntityType,
        Result,
    )

    def _log(action, entity_id, entity_name, description, current_user):
        session_local = get_session_local()
        with session_local() as session:
            try:
                AuditService.log(
                    db=session,
                    action_type=ActionType.EXECUTE,
                    entity_type=EntityType.HOST,
                    description=description,
                    result=Result.SUCCESS,
                    username=current_user,
                    entity_id=entity_id,
                    entity_name=entity_name,
                )
                session.commit()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("Observability audit log failed: %s", exc)
                session.rollback()

    return _log


def mount_observability_routes(app: FastAPI) -> bool:
    """Mount observability routes from observability_engine if available."""
    observability_engine = module_loader.get_module("observability_engine")
    if observability_engine is None:
        logger.debug(
            "observability_engine module not loaded, skipping observability routes"
        )
        return False

    module_info = observability_engine.get_module_info()
    if not module_info.get("provides_routes", False):
        logger.debug("observability_engine module does not provide routes")
        return False

    from backend.services.proplus_dispatch import enqueue_apply_plan

    try:
        with _cython_compat():
            router = observability_engine.get_observability_router(
                db_dependency=Depends(get_db),
                auth_dependency=Depends(get_current_user),
                feature_gate=_feature_dependency,
                module_gate=_module_dependency,
                models=models,
                http_exception=HTTPException,
                status_codes=status,
                logger=logger,
                dispatch_plan_fn=enqueue_apply_plan,
                audit_log_fn=_make_observability_audit_log_fn(),
            )
            app.include_router(router, prefix="/api")
        logger.info(
            "Mounted observability routes from observability_engine v%s",
            module_info.get("version", "unknown"),
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to mount observability routes: %s", exc)
        return False


def mount_multitenancy_routes(app: FastAPI) -> bool:
    """Mount the multi-tenancy control-plane router.

    Unlike the other engines, the control plane is gated on the deployment-level
    ``multitenancy.enabled`` flag — not a per-request license check — because it
    only exists when the operator has turned multi-tenancy on.  When the licensed
    ``multitenancy_engine`` is loaded, its router (the real logic) is mounted;
    otherwise the built-in OSS router is the fallback, so a config-only
    multi-tenant deployment keeps working without the engine.

    Mounted here (at startup, after module load) rather than in
    ``route_registration`` (import time) so the engine — which loads and is
    bridged into the seam during startup — has a chance to take over the route.
    """
    from backend.config import config as config_module  # noqa: PLC0415

    if not config_module.is_multitenancy_enabled():
        logger.debug("Multi-tenancy disabled; control-plane router not mounted")
        return False

    try:
        from backend.api import control_plane  # noqa: PLC0415
        from backend.multitenancy import seam  # noqa: PLC0415

        engine = seam.active_engine()
        router = (
            engine.control_plane_router()
            if engine is not None
            else control_plane.router
        )
        # The router self-prefixes "/control-plane"; mount it at the canonical
        # native "/api/v1" surface plus a hidden deprecated "/api" alias (Phase
        # 13.2.1), matching the _include_versioned pattern used by the OSS routes.
        app.include_router(router, prefix="/api/v1")
        app.include_router(router, prefix="/api", include_in_schema=False)
        logger.info(
            "Mounted multi-tenancy control-plane router (%s)",
            "licensed engine" if engine is not None else "OSS built-in",
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to mount multi-tenancy control-plane routes: %s", exc)
        return False
