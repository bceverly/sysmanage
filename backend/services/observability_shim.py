"""
Engine-first shim for observability deploy / remove operations.

Phase 10.2 step 7 Phase D: when the Pro+ ``observability_engine`` module
is loaded, the OSS endpoints at
``backend/api/opentelemetry/deployment.py`` route OTEL deploys through
the engine's multi-platform plan builders and dispatch via
``apply_deployment_plan`` — same path the engine's own
``/api/v1/observability/...`` routes use.  When the engine is not
loaded (free-tier deployments), the OSS endpoints fall back to the
legacy ``deploy_opentelemetry`` WS command path, which the agent's
``otel_deploy_*.py`` files continue to service.

The helpers here return ``Optional[str]`` (the queued message_id on
success, ``None`` to signal the caller should use its legacy path).
They never raise: callers always have a working fallback.

This decouples cutover from agent-side code deletion.  Once every
deployment topology has been verified on the engine path, the legacy
WS command handlers (and the per-platform ``otel_deploy_*.py``
modules) can be removed.  Until then they remain importable so the
free-tier path keeps working.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models

logger = logging.getLogger(__name__)


# Map ``host.platform`` (the agent reports ``platform.system()``) to the
# engine's platform tokens.  Linux is two-step because the engine
# distinguishes ``linux_apt`` vs ``linux_dnf`` based on which package
# manager the host actually uses — we look at the host's installed
# packages to pick.
_PLATFORM_TO_NONLINUX_ENGINE_TOKEN = {
    "freebsd": "freebsd",
    "openbsd": "openbsd",
    "netbsd": "netbsd",
    "darwin": "macos",
    "windows": "windows",
}


def _detect_otel_platform(host: models.Host, db: Session) -> Optional[str]:
    """Map an OSS Host record to an engine OTEL platform token.

    Returns one of ``SUPPORTED_OTEL_PLATFORMS`` (see
    ``observability_engine`` module) or ``None`` if the platform can't
    be determined — caller falls back to the legacy WS command.

    Linux distinction (apt vs dnf) samples the host's recorded
    installed packages.  If the host has no software inventory yet
    (e.g. fresh registration before the first collection cycle), we
    return ``None`` so the legacy path runs and the agent picks the
    right package manager at runtime via its own detection.
    """
    plat = (host.platform or "").strip().lower()
    if not plat:
        return None

    token = _PLATFORM_TO_NONLINUX_ENGINE_TOKEN.get(plat)
    if token is not None:
        return token

    if plat != "linux":
        return None

    # Sample the host's known package managers from its installed
    # software inventory.  ``distinct().limit(8)`` caps the query cost
    # — we only need to see one apt or dnf entry to decide.
    managers = {
        row[0]
        for row in db.query(models.SoftwarePackage.package_manager)
        .filter(models.SoftwarePackage.host_id == host.id)
        .distinct()
        .limit(8)
        .all()
        if row[0]
    }
    if "apt" in managers:
        return "linux_apt"
    if "dnf" in managers or "yum" in managers:
        return "linux_dnf"
    return None


def _engine_or_none():
    """Return the loaded observability_engine, or None if not licensed."""
    engine = module_loader.get_module("observability_engine")
    if engine is None:
        return None
    # ``get_module_info`` exists on every Pro+ engine; if it isn't there
    # something loaded an incompatible artifact and we should not call it.
    if not hasattr(engine, "build_otel_multiplatform_deploy_plan"):
        return None
    return engine


def try_engine_otel_deploy(
    host: models.Host,
    grafana_url: str,
    db: Session,
) -> Optional[str]:
    """Attempt the engine-driven OTEL deploy path.

    On success returns the queued message_id; on any failure (engine
    not loaded, undetectable platform, build/enqueue exception)
    returns ``None`` and the caller falls back to its legacy code
    path.  Never raises.
    """
    engine = _engine_or_none()
    if engine is None:
        return None

    platform_token = _detect_otel_platform(host, db)
    if platform_token is None:
        return None

    try:
        # Local import keeps this module importable in tests that
        # stub the dispatcher out.
        from backend.services.proplus_dispatch import enqueue_apply_plan

        req = engine.OtelMultiPlatformDeployRequest(
            platform=platform_token,
            grafana_url=grafana_url,
        )
        plan = engine.build_otel_multiplatform_deploy_plan(req)
        return enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=900)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Engine OTEL deploy path failed for host %s (platform=%s); "
            "falling back to legacy WS command: %s",
            host.id,
            platform_token,
            exc,
        )
        return None


_BSD_PLATFORM_TO_VARIANT = {
    "freebsd": "freebsd",
    "openbsd": "openbsd",
    "netbsd": "netbsd",
}


def try_engine_graylog_attach(
    host: models.Host,
    mechanism: str,
    graylog_server: str,
    port: int,
) -> Optional[str]:
    """Attempt the engine-driven Graylog attach path.

    Routes by host platform (no DB lookup needed — unlike the OTEL
    deploy path, which has to sample SoftwarePackage rows to decide
    apt-vs-dnf on Linux, Graylog's Linux plan auto-detects rsyslog
    vs syslog-ng at agent execute-time via ``systemctl is-active``):

      * Linux + syslog/gelf  → ``build_graylog_linux_autodetect_plan``
        (stages rsyslog AND syslog-ng configs, executes only the one
        whose daemon is active)
      * \\*BSD + syslog_*    → ``build_graylog_bsd_syslog_append_plan``
        (sed-strips any prior block, appends fresh forward line,
        restarts variant's syslogd)
      * anything else        → ``None`` (Windows sidecar needs api_token
        / node_id which the OSS endpoint doesn't currently accept; fall
        back to legacy ``ATTACH_TO_GRAYLOG`` WS command)

    Returns the queued message_id on success, ``None`` on any failure
    so the caller's legacy fallback runs.  Never raises.
    """
    engine = _engine_or_none()
    if engine is None:
        return None
    if not hasattr(engine, "build_graylog_linux_autodetect_plan"):
        return None
    if not hasattr(engine, "build_graylog_bsd_syslog_append_plan"):
        return None

    plat = (host.platform or "").strip().lower()
    if not plat:
        return None

    try:
        from backend.services.proplus_dispatch import enqueue_apply_plan

        if plat == "linux":
            req = engine.GraylogRsyslogRequest(
                graylog_server=graylog_server,
                port=port,
                mechanism=mechanism,
            )
            plan = engine.build_graylog_linux_autodetect_plan(req)
        elif plat in _BSD_PLATFORM_TO_VARIANT:
            req = engine.GraylogBsdSyslogAppendRequest(
                graylog_server=graylog_server,
                port=port,
                mechanism=mechanism,
                bsd_variant=_BSD_PLATFORM_TO_VARIANT[plat],
            )
            plan = engine.build_graylog_bsd_syslog_append_plan(req)
        else:
            return None

        return enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=600)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Engine Graylog attach path failed for host %s (platform=%s, "
            "mechanism=%s); falling back to legacy WS command: %s",
            host.id,
            plat,
            mechanism,
            exc,
        )
        return None


def try_engine_otel_remove(host: models.Host, db: Session) -> Optional[str]:
    """Attempt the engine-driven OTEL remove path; see ``try_engine_otel_deploy``."""
    engine = _engine_or_none()
    if engine is None or not hasattr(engine, "build_otel_multiplatform_remove_plan"):
        return None

    platform_token = _detect_otel_platform(host, db)
    if platform_token is None:
        return None

    try:
        from backend.services.proplus_dispatch import enqueue_apply_plan

        plan = engine.build_otel_multiplatform_remove_plan(platform_token)
        return enqueue_apply_plan(host_id=str(host.id), plan=plan, timeout=600)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Engine OTEL remove path failed for host %s (platform=%s); "
            "falling back to legacy WS command: %s",
            host.id,
            platform_token,
            exc,
        )
        return None
