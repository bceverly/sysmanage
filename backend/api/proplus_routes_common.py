# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Shared dependency-gate factories and the Cython compatibility shim for the
Pro+ route-mounting modules.

Extracted from ``backend.api.proplus_routes`` so the per-engine mount functions
(split across ``proplus_routes`` + ``proplus_routes_mounts``) can share them
without a circular import.  ``proplus_routes`` re-exports ``_feature_dependency``
/ ``_module_dependency`` / ``_cython_compat`` so its public surface (and test
references) are unchanged.
"""

from contextlib import contextmanager

import fastapi
import fastapi.dependencies.utils as _dep_utils
import fastapi.params
from fastapi import HTTPException, status

from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.license_service import license_service
from backend.licensing.module_loader import module_loader
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
