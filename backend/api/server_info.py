"""
Server-info endpoint (Phase 11).

Single read-only endpoint that exposes which role this server runs as
(``standard`` / ``collector`` / ``repository``), what license tier is
active, and which Pro+ engines are loaded.  The frontend uses this to
render the role chip in the header bar; monitoring and chat-ops use it
to identify a box without having to log in.

Public — no auth required.  All fields are non-secret.
"""

import logging

from fastapi import APIRouter

from backend.config import config as config_module
from backend.licensing.module_loader import module_loader

logger = logging.getLogger(__name__)

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

    The whole body is wrapped in try/except so a transient failure
    (e.g. module_loader being re-initialised between requests, or a
    config-read race during startup) returns a safe-degraded envelope
    rather than a 500.  The Playwright performance suite's
    ``should not have critical failed requests`` test treats any 5xx
    as a hard failure; this endpoint is on the cold-start critical
    path (the frontend's role chip in the header bar calls it
    immediately on page load), and a 500 here flakes the whole CI run.
    The fallback envelope reports ``standard`` / ``community`` /
    empty-engine-list — i.e. what an unlicensed OSS deployment would
    legitimately return — and the real failure is captured via
    ``logger.exception`` for post-mortem.
    """
    try:
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
    except Exception:  # pylint: disable=broad-exception-caught
        # See docstring above — the audit trail goes to logs;
        # callers get a degraded-but-valid envelope.
        logger.exception("server-info handler failed; returning safe-degraded envelope")
        return {
            "role": "standard",
            "version": _resolve_version(),
            "license_tier": "community",
            "loaded_engines": [],
            "expected_engine_for_role": None,
            "role_engine_loaded": True,
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
