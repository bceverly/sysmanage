# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Feature and module gating decorators for Pro+ licensing.

Provides decorators to restrict access to Pro+ features and modules.

A missing license answers HTTP 402 (Payment Required), the same code every
other licensed surface uses, with ``detail.error == "pro_plus_required"``.
These gates answered 403 until the Phase 25 edition audit (2026-11-14), so an
unlicensed caller -- or a Professional license asking for an Enterprise
feature -- read "forbidden" instead of "needs a license"; the route walk in
tests/test_tier_gates_walk.py now holds every route to 402.
"""

import asyncio
import functools
from typing import Callable, Optional

from fastapi import HTTPException, status

from backend.licensing.features import FeatureCode, LicenseTier, ModuleCode
from backend.licensing.license_service import license_service
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.feature_gate")


class LicenseRequiredError(Exception):
    """Exception raised when a Pro+ license is required but not available."""

    def __init__(
        self, message: str, feature: Optional[str] = None, module: Optional[str] = None
    ):
        super().__init__(message)
        self.feature = feature
        self.module = module


def requires_feature(feature: FeatureCode | str) -> Callable:
    """
    Decorator to require a specific Pro+ feature.

    Usage:
        @requires_feature(FeatureCode.HEALTH_ANALYSIS)
        async def get_health_analysis():
            ...

    Args:
        feature: The required feature code

    Returns:
        Decorated function that checks for the feature before execution

    Raises:
        HTTPException: 402 if the feature is not licensed
    """
    # Convert string to FeatureCode if needed
    if isinstance(feature, str):
        try:
            feature_code = FeatureCode(feature)
        except ValueError as exc:
            raise ValueError(f"Unknown feature code: {feature}") from exc
    else:
        feature_code = feature

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not license_service.has_feature(feature_code):
                logger.warning(
                    "Access denied to feature '%s' - Pro+ license required",
                    feature_code.value,
                )
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "pro_plus_required",
                        "message": f"This feature requires a Pro+ license with '{feature_code.value}' enabled",
                        "feature": feature_code.value,
                    },
                )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not license_service.has_feature(feature_code):
                logger.warning(
                    "Access denied to feature '%s' - Pro+ license required",
                    feature_code.value,
                )
                raise LicenseRequiredError(
                    f"This feature requires a Pro+ license with '{feature_code.value}' enabled",
                    feature=feature_code.value,
                )
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def license_required_error(module_code: ModuleCode) -> HTTPException:
    """402: the license does not include ``module_code``."""
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "error": "pro_plus_required",
            "message": f"This feature requires a Pro+ license with '{module_code.value}' module",
            "module": module_code.value,
        },
    )


def module_unavailable_error(module_code: ModuleCode) -> HTTPException:
    """503: licensed, but the engine is not loaded -- an administrator's
    problem, not a sales one."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "module_not_available",
            "message": f"The '{module_code.value}' module is not currently available",
            "module": module_code.value,
        },
    )


def refuse_unlicensed_write(module: ModuleCode | str) -> HTTPException:
    """What a write to a licensed stub answers (the engine is absent, which is
    why its stub is mounted): 402 without the license, 503 with it.

    The stubs used to answer every call ``200 {"licensed": false}``.  For a
    read that is a usable "nothing here, and why"; for a write it told a
    script that deploying, deleting or dispatching had worked (Phase 25
    edition audit, 2026-11-14).
    """
    module_code = ModuleCode(module) if isinstance(module, str) else module
    if not license_service.has_module(module_code):
        return license_required_error(module_code)
    return module_unavailable_error(module_code)


def _check_module_licensed_http(module_code: ModuleCode) -> None:
    """Check if module is licensed, raising HTTPException if not."""
    if not license_service.has_module(module_code):
        logger.warning(
            "Access denied to module '%s' - Pro+ license required",
            module_code.value,
        )
        raise license_required_error(module_code)


def _check_module_loaded_http(module_code: ModuleCode) -> None:
    """Check if module is loaded, raising HTTPException if not."""
    from backend.licensing.module_loader import module_loader

    if not module_loader.is_module_loaded(module_code.value):
        logger.warning(
            "Module '%s' is licensed but not loaded",
            module_code.value,
        )
        raise module_unavailable_error(module_code)


def _check_module_licensed_sync(module_code: ModuleCode) -> None:
    """Check if module is licensed, raising LicenseRequiredError if not."""
    if not license_service.has_module(module_code):
        logger.warning(
            "Access denied to module '%s' - Pro+ license required",
            module_code.value,
        )
        raise LicenseRequiredError(
            f"This feature requires a Pro+ license with '{module_code.value}' module",
            module=module_code.value,
        )


def _check_module_loaded_sync(module_code: ModuleCode) -> None:
    """Check if module is loaded, raising LicenseRequiredError if not."""
    from backend.licensing.module_loader import module_loader

    if not module_loader.is_module_loaded(module_code.value):
        raise LicenseRequiredError(
            f"The '{module_code.value}' module is not currently available",
            module=module_code.value,
        )


def require_module(module: ModuleCode | str) -> None:
    """Imperative form of ``requires_module``, for gates that depend on INPUT.

    The decorator and the ``Depends`` factory both decide before the handler
    sees the request, which is fine when a whole endpoint is licensed. It does
    not work when the gate depends on the PAYLOAD -- applying a config profile
    is free with ansible-core and licensed with Puppet/Salt/Chef, so the engine
    named in the body decides. Calling this inline keeps that decision in one
    place instead of tempting callers into ``_check_module_*`` privates.

    Raises:
        HTTPException: 402 if unlicensed, 503 if licensed but not loaded.
    """
    if isinstance(module, str):
        try:
            module_code = ModuleCode(module)
        except ValueError as exc:
            raise ValueError(f"Unknown module code: {module}") from exc
    else:
        module_code = module
    _check_module_licensed_http(module_code)
    _check_module_loaded_http(module_code)


def requires_module(module: ModuleCode | str) -> Callable:
    """
    Decorator to require a specific Pro+ module.

    This decorator checks both that the module is licensed AND that it has been
    successfully loaded. Use this for endpoints that depend on Cython modules.

    Usage:
        @requires_module(ModuleCode.HEALTH_ENGINE)
        async def analyze_health():
            health_engine = module_loader.get_module("health_engine")
            ...

    Args:
        module: The required module code

    Returns:
        Decorated function that checks for the module before execution

    Raises:
        HTTPException: 402 if the module is not licensed
    """
    # Convert string to ModuleCode if needed
    if isinstance(module, str):
        try:
            module_code = ModuleCode(module)
        except ValueError as exc:
            raise ValueError(f"Unknown module code: {module}") from exc
    else:
        module_code = module

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            _check_module_licensed_http(module_code)
            _check_module_loaded_http(module_code)
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            _check_module_licensed_sync(module_code)
            _check_module_loaded_sync(module_code)
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def require_module_loaded(module: ModuleCode | str) -> Callable:
    """Build a ``Depends``-friendly dependency that gates on a module.

    Unlike ``requires_module`` (which is a *decorator* applied to a
    handler function), this returns a no-arg callable suitable for
    FastAPI router-level ``dependencies=[Depends(...)]`` lists.  That
    lets a whole router (e.g. access groups, registration keys) be
    gated in one place instead of decorating every handler.

    Raises HTTP 402 when the calling license doesn't include the
    module, or 503 when the license has it but the Cython engine
    isn't loaded -- same response shape as the decorator path so
    clients can branch on ``detail.error`` uniformly.

    Usage:
        router = APIRouter(
            ...,
            dependencies=[
                Depends(require_module_loaded(ModuleCode.FEDERATION_CONTROLLER_ENGINE))
            ],
        )

    Phase 12.4 uses this to fold the OSS access-groups + registration-keys
    surface behind the federation controller engine; see ROADMAP §12.4.
    """
    if isinstance(module, str):
        try:
            module_code = ModuleCode(module)
        except ValueError as exc:
            raise ValueError(f"Unknown module code: {module}") from exc
    else:
        module_code = module

    def _check_module_gate() -> None:
        _check_module_licensed_http(module_code)
        _check_module_loaded_http(module_code)

    # Naming the function helps FastAPI's OpenAPI generation produce a
    # readable dependency name in the spec, and pylint stops flagging
    # the inner def as anonymous.
    _check_module_gate.__name__ = f"require_module_loaded__{module_code.value}"
    return _check_module_gate


def _pro_plus_for_caller() -> bool:
    """Any paid license -- and, on a multi-tenant server, a paid edition for
    the tenant in scope.  ``is_pro_plus_active`` alone let a Community tenant
    of a SaaS-licensed server through every "any Pro+ license" gate, which
    the module and feature gates already narrow by edition (13.1.J; found by
    the edition route walk, 2026-11-14)."""
    if not license_service.is_pro_plus_active:
        return False
    # Local import: the seam reaches the multitenancy engine (see
    # LicenseService._allowed_for_active_tenant_edition).
    from backend.services.tenant_edition import (  # noqa: PLC0415
        edition_for_active_tenant,
    )

    return edition_for_active_tenant() != LicenseTier.COMMUNITY.value


def requires_pro_plus() -> Callable:
    """
    Decorator to require any active Pro+ license.

    This is a simpler check that just verifies Pro+ is active,
    without checking for specific features or modules.

    Usage:
        @requires_pro_plus()
        async def get_pro_plus_only_data():
            ...

    Returns:
        Decorated function that checks for Pro+ license

    Raises:
        HTTPException: 402 if Pro+ is not active
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not _pro_plus_for_caller():
                logger.warning("Access denied - Pro+ license required")
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "pro_plus_required",
                        "message": "This feature requires a Pro+ license",
                    },
                )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not _pro_plus_for_caller():
                logger.warning("Access denied - Pro+ license required")
                raise LicenseRequiredError("This feature requires a Pro+ license")
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
