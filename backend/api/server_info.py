"""
Server-info endpoint (Phase 11).

Single read-only endpoint that exposes which role this server runs as
(``standard`` / ``collector`` / ``repository``), what license tier is
active, and which Pro+ engines are loaded.  The frontend uses this to
render the role chip in the header bar; monitoring and chat-ops use it
to identify a box without having to log in.

Public — no auth required.  All fields are non-secret.
"""

from fastapi import APIRouter

from backend.config import config as config_module
from backend.licensing.module_loader import module_loader

router = APIRouter(prefix="/api/v1", tags=["server-info"])


_AIRGAP_ENGINE_FOR_ROLE = {
    "collector": "airgap_collector_engine",
    "repository": "airgap_repository_engine",
}


@router.get("/server-info")
def get_server_info():
    """Return non-secret identity + capability info about this server.

    Shape::

        {
          "role": "standard" | "collector" | "repository",
          "version": "2.3.0.0",
          "license_tier": "community" | "professional" | "enterprise",
          "loaded_engines": ["automation_engine", ...],
          "expected_engine_for_role": "airgap_collector_engine" | null,
          "role_engine_loaded": true | false
        }

    ``role_engine_loaded`` is the headline air-gap health check: when
    role is ``collector`` or ``repository``, this is ``true`` only when
    the corresponding Pro+ engine is currently loaded.  When role is
    ``standard``, it's always ``true`` (no role-specific engine
    required).
    """
    role = config_module.get_server_role()
    loaded = sorted(module_loader.loaded_modules.keys())
    expected_engine = _AIRGAP_ENGINE_FOR_ROLE.get(role)
    role_engine_loaded = expected_engine is None or expected_engine in loaded
    license_tier = _resolve_license_tier()

    return {
        "role": role,
        "version": _resolve_version(),
        "license_tier": license_tier,
        "loaded_engines": loaded,
        "expected_engine_for_role": expected_engine,
        "role_engine_loaded": role_engine_loaded,
    }


def _resolve_version() -> str:
    """Best-effort sysmanage version string."""
    try:
        from backend import __version__  # type: ignore

        return str(__version__)
    except (ImportError, AttributeError):
        return "unknown"


def _resolve_license_tier() -> str:
    """Best-effort license tier — falls back to ``community`` if no
    license is configured or the licensing service can't be reached."""
    try:
        from backend.licensing.license_service import (  # type: ignore
            get_active_tier,
        )

        tier = get_active_tier()
        if tier is None:
            return "community"
        return str(getattr(tier, "value", tier))
    except Exception:  # pylint: disable=broad-exception-caught
        # Catches ImportError + AttributeError + everything the
        # licensing service might raise.  Best-effort fallback:
        # callers care about the ``community`` default, not the
        # specific failure mode.
        return "community"
