# pylint: disable=too-many-lines
"""
Pro+ Route Mounting - Thin Wrappers for Cython Modules

This module provides thin wrappers that mount routes from compiled
Cython modules (vuln_engine, health_engine) when available.

The actual route implementations, service logic, and business rules
are all contained within the compiled modules.
"""

from contextlib import contextmanager

import fastapi
import fastapi.dependencies.utils as _dep_utils
import fastapi.params
from fastapi import Depends, FastAPI, HTTPException, status

from backend.auth.auth_bearer import get_current_user
from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db, get_session_local
from backend.services.email_service import email_service
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.proplus_routes")


# ---------------------------------------------------------------------------
# Dependency-compatible feature/module gate factories
#
# Cython modules call feature_gate(code) and module_gate(code), then use
# the result with Depends().  The original requires_feature / requires_module
# return *decorators* whose (func: Callable) parameter FastAPI interprets as
# a required query parameter, causing 422 errors.
#
# These replacements return zero-argument async callables that work cleanly
# as FastAPI dependencies.
# ---------------------------------------------------------------------------


def _feature_dependency(feature):
    """Return a callable that works both as a decorator and a Depends() dependency.

    - Decorator mode: called with an endpoint function → wraps it with a license check
    - Dependency mode: called with no args by FastAPI Depends() → checks license directly

    The __signature__ is overridden to show zero parameters so FastAPI does not
    add a spurious ``func`` query parameter.
    """
    import asyncio
    import functools
    import inspect

    feature_code = FeatureCode(feature) if isinstance(feature, str) else feature

    def _raise():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "pro_plus_required",
                "message": (
                    f"This feature requires a Pro+ license "
                    f"with '{feature_code.value}' enabled"
                ),
                "feature": feature_code.value,
            },
        )

    def _check():
        if not license_service.has_feature(feature_code):
            _raise()

    def _wrap(func):
        """Wrap a function (sync or async) with a license check."""
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                _check()
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _check()
            return func(*args, **kwargs)

        return sync_wrapper

    def gate(func=None):
        if func is not None and callable(func):
            return _wrap(func)
        # Dependency mode (called by FastAPI Depends with no args)
        _check()

    # Hide the func parameter from FastAPI's signature inspection
    gate.__signature__ = inspect.Signature(parameters=[])
    return gate


def _module_dependency(module):
    """Return a callable that works both as a decorator and a Depends() dependency.

    Same dual-purpose pattern as _feature_dependency but checks module
    licensing AND loading.
    """
    import asyncio
    import functools
    import inspect

    module_code = ModuleCode(module) if isinstance(module, str) else module

    def _raise_license():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "pro_plus_required",
                "message": (
                    f"This feature requires a Pro+ license "
                    f"with '{module_code.value}' module"
                ),
                "module": module_code.value,
            },
        )

    def _raise_unavailable():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "module_not_available",
                "message": (
                    f"The '{module_code.value}' module is not currently available"
                ),
                "module": module_code.value,
            },
        )

    def _check():
        if not license_service.has_module(module_code):
            _raise_license()
        if not module_loader.is_module_loaded(module_code.value):
            _raise_unavailable()

    def _wrap(func):
        """Wrap a function (sync or async) with a module check."""
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                _check()
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _check()
            return func(*args, **kwargs)

        return sync_wrapper

    def gate(func=None):
        if func is not None and callable(func):
            return _wrap(func)
        # Dependency mode
        _check()

    gate.__signature__ = inspect.Signature(parameters=[])
    return gate


# ---------------------------------------------------------------------------
# Cython module compatibility layer
#
# Compiled Cython modules use typed variable assignments (cdef int, cdef str)
# that require exact type matches. FastAPI's Query() returns FieldInfo objects
# which fail Cython's PyUnicode_ExactCheck / PyLong_ExactCheck.
#
# Additionally, newer Cython modules internally wrap dependencies with
# Depends(), so passing Depends(get_db) would create double-wrapping:
# Depends(Depends(get_db)).
#
# This shim temporarily:
#   1. Replaces fastapi.Query with a factory that returns plain str/int
#      values (passing Cython type checks) while stashing the real FieldInfo
#      in a registry keyed by object id.
#   2. Patches FastAPI's analyze_param to swap the stashed FieldInfo back in
#      before FastAPI processes route parameters.
# ---------------------------------------------------------------------------

_query_registry: dict = {}
_query_state = {"counter": 0}


def _compat_query_factory(default=fastapi.params._Unset, **kwargs):  # noqa: SLF001
    """Query factory returning plain int/str for Cython type checks."""
    real_fi = _original_query_func(default=default, **kwargs)

    if isinstance(default, int) and not isinstance(default, bool):
        val = int(default)
        _query_registry[id(val)] = real_fi
        return val

    # For str, None, and PydanticUndefined defaults: return a unique
    # non-interned str so Cython's PyUnicode_ExactCheck passes and
    # the id is unique for registry lookup.
    _query_state["counter"] += 1
    val = "\x00_q" + str(_query_state["counter"])
    _query_registry[id(val)] = real_fi
    return val


def _patched_analyze_param(*, param_name, annotation, value, is_path_param):
    """Recover stashed FieldInfo before FastAPI processes the parameter."""
    fi = _query_registry.get(id(value))
    if fi is not None:
        value = fi
    return _original_analyze_param(
        param_name=param_name,
        annotation=annotation,
        value=value,
        is_path_param=is_path_param,
    )


# Store originals at import time
_original_query_func = fastapi.Query
_original_analyze_param = _dep_utils.analyze_param


@contextmanager
def _cython_compat():
    """Context manager that enables Cython module compatibility patches."""
    _query_registry.clear()
    fastapi.Query = _compat_query_factory
    _dep_utils.analyze_param = _patched_analyze_param
    try:
        yield
    finally:
        _dep_utils.analyze_param = _original_analyze_param
        fastapi.Query = _original_query_func
        _query_registry.clear()


# ---------------------------------------------------------------------------
# Cython Module Route Mounting
#
# Standard pattern for all Cython modules:
#   1. Wrap with _cython_compat() — patches Query() to return plain int/str
#      values that satisfy Cython's cdef type checks (harmless when unused).
#   2. Pass Depends(get_db) and Depends(get_current_user) pre-wrapped.
#
# EXCEPTION: reporting_engine v1.1.0 internally calls Depends() on the
# passed dependencies, so it receives raw get_db / get_current_user to
# avoid double-wrapping.  This should be fixed in a future recompile.
# ---------------------------------------------------------------------------


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
        logger.error("Failed to mount vulnerability routes: %s", e)
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
        logger.error("Failed to mount health routes: %s", e)
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
        logger.error("Failed to mount compliance routes: %s", e)
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
        logger.error("Failed to mount alerting routes: %s", e)
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
        logger.error("Failed to mount reporting routes: %s", e)
        return False


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
        logger.error("Failed to mount audit routes: %s", e)
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
        logger.error(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
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
        logger.error("Failed to mount container routes: %s", e)
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
        logger.error("Failed to mount AV management routes: %s", e)
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
        logger.error("Failed to mount firewall orchestration routes: %s", e)
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
        logger.error("Failed to mount automation routes: %s", e)
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
        logger.error("Failed to mount fleet routes: %s", e)
        return False


def mount_proplus_stub_routes(app: FastAPI, results: dict) -> None:
    """
    Mount stub routes for Pro+ modules that weren't loaded.

    When a Pro+ module isn't available (no license), its frontend plugin
    may still be loaded and attempt API calls. These stubs return
    {"licensed": false} with HTTP 200 so the frontend can display
    a clean "license required" message instead of a 404 error.

    Args:
        app: The FastAPI application instance
        results: Dictionary of module mount results from mount_proplus_routes
    """
    from fastapi import APIRouter

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

    if stubs_mounted > 0:
        logger.info(
            "Mounted %d Pro+ stub route group(s) for unlicensed modules",
            stubs_mounted,
        )


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
    }

    mounted_count = sum(1 for v in results.values() if v)
    if mounted_count > 0:
        logger.info("Mounted %d Pro+ module route(s)", mounted_count)
    else:
        logger.debug("No Pro+ module routes mounted")

    # Mount stub routes for any modules that weren't loaded
    mount_proplus_stub_routes(app, results)

    return results
