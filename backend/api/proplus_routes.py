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
        return None

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
        return None

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

        # GPG Key Management relocated into the licensed secrets_engine (Pro+
        # moat).  Without the engine, these sub-paths serve the licensed-stub so
        # /api/v1/secrets/gpg-keys* returns {"licensed": False} rather than 404.
        @router.get("/gpg-keys")
        async def gpg_keys_list_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "gpg_keys": []}

        @router.post("/gpg-keys")
        async def gpg_keys_upload_stub(
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/gpg-keys/{key_id}")
        async def gpg_keys_get_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/gpg-keys/{key_id}")
        async def gpg_keys_delete_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.get("/gpg-keys/{key_id}/assignments")
        async def gpg_keys_list_assignments_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False, "assignments": []}

        @router.post("/gpg-keys/{key_id}/assignments")
        async def gpg_keys_create_assignment_stub(
            key_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

        @router.delete("/gpg-keys/{key_id}/assignments/{assignment_id}")
        async def gpg_keys_delete_assignment_stub(
            key_id: str,
            assignment_id: str,
            current_user=Depends(get_current_user),
        ):
            return {"licensed": False}

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

    if not results.get("virtualization_engine"):
        from fastapi import APIRouter

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
        from fastapi import APIRouter

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
        from fastapi import APIRouter

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
        from fastapi import APIRouter

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
