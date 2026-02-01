"""
Feature and module gating decorators for Pro+ licensing.

Provides decorators to restrict access to Pro+ features and modules.
"""

import asyncio
import functools
from typing import Callable, Optional

from fastapi import HTTPException, status

from backend.licensing.features import FeatureCode, ModuleCode
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
        HTTPException: 403 if the feature is not available
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
                    status_code=status.HTTP_403_FORBIDDEN,
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


def _check_module_licensed_http(module_code: ModuleCode) -> None:
    """Check if module is licensed, raising HTTPException if not."""
    if not license_service.has_module(module_code):
        logger.warning(
            "Access denied to module '%s' - Pro+ license required",
            module_code.value,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "pro_plus_required",
                "message": f"This feature requires a Pro+ license with '{module_code.value}' module",
                "module": module_code.value,
            },
        )


def _check_module_loaded_http(module_code: ModuleCode) -> None:
    """Check if module is loaded, raising HTTPException if not."""
    from backend.licensing.module_loader import module_loader

    if not module_loader.is_module_loaded(module_code.value):
        logger.warning(
            "Module '%s' is licensed but not loaded",
            module_code.value,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "module_not_available",
                "message": f"The '{module_code.value}' module is not currently available",
                "module": module_code.value,
            },
        )


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
        HTTPException: 403 if the module is not available
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
        HTTPException: 403 if Pro+ is not active
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not license_service.is_pro_plus_active:
                logger.warning("Access denied - Pro+ license required")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "pro_plus_required",
                        "message": "This feature requires a Pro+ license",
                    },
                )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not license_service.is_pro_plus_active:
                logger.warning("Access denied - Pro+ license required")
                raise LicenseRequiredError("This feature requires a Pro+ license")
            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
