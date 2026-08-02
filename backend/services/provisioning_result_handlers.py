# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Result handlers for provisioning_engine agent plans (Phase 18.2 S1).

The bare-metal readiness preflight runs ON a managed host (the designated
provisioning server), so unlike compute provisioning — which actuates a
provider API from the control plane — it goes through the normal
``apply_deployment_plan`` agent path.  The engine's route stamps an in-flight
message id; when the agent's command_result lands,
``proplus_dispatch.route_proplus_command_result`` calls in here and we upsert
``provisioning_readiness``.

Deliberately mirrors ``repo_mirror_result_handlers`` (the Phase 10.4.1
setup-status card) so the two async probe flows stay recognisably the same.
"""

import logging
from typing import Any, Dict

from backend.persistence import db, models
from backend.services.firewall_plan_builder import detect_firewall_flavor

logger = logging.getLogger(__name__)

# Values the probe may report for a tool/file key.
_PRESENCE_VALUES = ("present", "missing")
# Values the probe may report for a listening-port key.
_LISTENER_VALUES = ("in_use", "free", "unknown")


def _parse_preflight_stdout(stdout: str) -> Dict[str, Any]:
    """Parse the readiness probe's ``key=value`` lines.

    Unknown keys are ignored rather than stored: the probe is the only writer
    of this row, so anything unrecognised means the agent ran a probe from a
    different engine version and we would rather keep the old value than
    record a key no reader understands.
    """
    tools: Dict[str, str] = {}
    services: Dict[str, str] = {}
    platform = None
    distro = None
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value in _PRESENCE_VALUES:
            tools[key] = value
        elif value in _LISTENER_VALUES:
            services[key] = value
        elif key == "platform":
            platform = value[:40]
        elif key == "distro":
            distro = value[:40]
    return {
        "tools": tools,
        "services": services,
        "platform": platform,
        "distro": distro,
    }


def _readiness_row(session, host_id: str):
    row = (
        session.query(models.ProvisioningReadiness)
        .filter(models.ProvisioningReadiness.host_id == host_id)
        .first()
    )
    if row is None:
        row = models.ProvisioningReadiness(host_id=host_id)
        session.add(row)
    return row


def _stamp_firewall_flavor(session, row, host_id: str) -> None:
    """Cache the host's firewall flavor so the advisor needn't re-derive it.

    Best-effort: a missing host row (or a probe that arrived after the host was
    deleted) leaves the flavor as-is rather than failing the whole result.
    """
    host = session.query(models.Host).filter(models.Host.id == host_id).first()
    if host is None:
        logger.warning(
            "provisioning preflight result for unknown host %s; "
            "firewall flavor not stamped",
            host_id,
        )
        return
    row.firewall_flavor = detect_firewall_flavor(host.platform, host.platform_release)


def _apply_provisioning_preflight(session, host_id: str, outcome: Dict[str, Any]):
    """Upsert ``provisioning_readiness`` from the probe's stdout."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _now_naive

    parsed = _parse_preflight_stdout(outcome["stdout"])
    row = _readiness_row(session, host_id)
    row.tools = parsed["tools"]
    row.services = parsed["services"]
    row.platform = parsed["platform"] or row.platform
    row.distro = parsed["distro"] or row.distro
    row.last_check_at = _now_naive()
    row.last_check_message_id = None  # probe completed; clear in-flight marker
    if outcome["status"] == "succeeded":
        row.last_check_error = None
        _stamp_firewall_flavor(session, row, host_id)
    else:
        row.last_check_error = (
            outcome["stderr"] or outcome["error"] or "probe failed"
        )[:8000]


def _apply_provisioning_install(session, host_id: str, outcome: Dict[str, Any]):
    """Stamp install_status + clear the in-flight marker."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _now_naive

    row = _readiness_row(session, host_id)
    row.last_install_at = _now_naive()
    row.last_install_message_id = None
    if outcome["status"] == "succeeded":
        row.install_status = "succeeded"
        row.last_install_error = None
    else:
        row.install_status = "failed"
        row.last_install_error = (
            outcome["stderr"] or outcome["error"] or "install failed"
        )[:8000]


def _apply_provisioning_apply(session, host_id: str, outcome: Dict[str, Any]):
    """Stamp apply_status for a config-advisor apply."""
    # pylint: disable=import-outside-toplevel
    from backend.services.proplus_dispatch import _now_naive

    row = _readiness_row(session, host_id)
    row.last_apply_at = _now_naive()
    row.last_apply_message_id = None
    if outcome["status"] == "succeeded":
        row.apply_status = "succeeded"
        row.last_apply_error = None
    else:
        row.apply_status = "failed"
        row.last_apply_error = (
            outcome["stderr"] or outcome["error"] or "apply failed"
        )[:8000]


_ACTION_HANDLERS = {
    "provisioning_preflight": _apply_provisioning_preflight,
    "provisioning_install": _apply_provisioning_install,
    "provisioning_apply": _apply_provisioning_apply,
}


def _apply_provisioning_op_result(
    primary_id: str, host_id: str, outcome: Dict[str, Any]
) -> None:
    """Handle completion of a provisioning_engine readiness plan.

    ``primary_id`` is the bare action — the row is keyed by host alone, so
    unlike repo-mirror ops there is no second id to encode.
    """
    handler = _ACTION_HANDLERS.get(primary_id)
    if handler is None:
        logger.warning(
            "Unknown provisioning_op action %r (host_id=%s); result dropped",
            primary_id,
            host_id,
        )
        return

    session_local = db.get_session_local()
    with session_local() as session:
        handler(session, host_id, outcome)
        session.commit()

    if primary_id == "provisioning_install" and outcome["status"] == "succeeded":
        _queue_followup_preflight(host_id, session_local)


def _queue_followup_preflight(host_id: str, session_local) -> None:
    """Auto-chain a probe after a successful install so the card reflects the
    new tool presence without a manual refresh.

    Stamps ``last_check_message_id`` before returning: the frontend polls while
    an in-flight marker is set, so leaving it NULL would stop the poll before
    the auto-probe's result lands.
    """
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader
    from backend.services.proplus_dispatch import (
        _register_correlation,
        enqueue_apply_plan,
    )

    try:
        engine = module_loader.get_module("provisioning_engine")
        if engine is None:
            logger.warning(
                "provisioning_engine no longer loaded; skipping the follow-up "
                "readiness probe for host %s",
                host_id,
            )
            return
        plan = engine.build_provisioning_preflight_plan()
        msg_id = enqueue_apply_plan(host_id=str(host_id), plan=plan, timeout=60)
        _register_correlation(
            msg_id, "provisioning_op", "provisioning_preflight", str(host_id)
        )
        with session_local() as session:
            row = _readiness_row(session, host_id)
            row.last_check_message_id = msg_id
            session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to queue follow-up readiness probe for host %s: %s",
            host_id,
            exc,
        )
