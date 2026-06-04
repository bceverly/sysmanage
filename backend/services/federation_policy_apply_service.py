"""
Site-side application of coordinator-pushed policies (Phase 12.2).

The coordinator defines policies centrally (``update_profile``,
``firewall_role``, …) and pushes them down; they land in the
``federation_received_policies`` inbox as ``applied=False`` (see
``federation_inbox_service``).  This module is the **apply worker** the
inbox docstrings refer to: it drains the unapplied policies each tick
and *materialises* each one into the site's own local tables — e.g. a
``firewall_role`` policy becomes a real row in the site's
``firewall_role`` table, exactly as if a local operator had created it.

Architecture: materialisation is a LOCAL database write only — no
network call.  The coordinator → site transport is already queued
(the push worker), and any agent-facing effect of a materialised
policy (e.g. assigning a firewall role to hosts) flows through the
existing queued command path.  So this module never calls out
directly; it just writes local rows and records apply status.

Policy types are handled by a pluggable applier registry
(:data:`_APPLIERS`).  An unregistered ``policy_type`` is recorded as a
structured apply error and left ``applied=False`` (visible + retried on
the next tick) rather than silently marked done — same honesty
contract as the command-fanout service's unsupported-command handling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import federation_inbox_service as inbox_svc

logger = logging.getLogger(__name__)

# policy_type -> applier(session, definition) -> None.  An applier
# materialises the policy into local tables and may raise on bad input;
# the worker turns a raise into a recorded apply error.
_APPLIERS: Dict[str, Callable[[Session, Dict[str, Any]], None]] = {}


class PolicyApplyError(Exception):
    """Raised by an applier when a policy definition can't be materialised."""


def register_applier(
    policy_type: str, applier: Callable[[Session, Dict[str, Any]], None]
) -> None:
    """Register (or override) the applier for ``policy_type``."""
    _APPLIERS[policy_type] = applier


# ---------------------------------------------------------------------
# firewall_role applier
# ---------------------------------------------------------------------


def _coerce_port(entry: Any) -> Dict[str, Any]:
    """Normalise one open-port spec from a policy definition.

    Accepts the full ``{port_number, tcp, udp, ipv4, ipv6}`` form or a
    bare integer port.  Mirrors the defaults of the local
    firewall-role create path (tcp on, udp off, both IP families).
    """
    if isinstance(entry, int):
        return {
            "port_number": entry,
            "tcp": True,
            "udp": False,
            "ipv4": True,
            "ipv6": True,
        }
    if not isinstance(entry, dict) or "port_number" not in entry:
        raise PolicyApplyError(f"invalid open_port spec: {entry!r}")
    port = entry["port_number"]
    if not isinstance(port, int) or port < 0 or port > 65535:
        raise PolicyApplyError(f"port_number out of range: {port!r}")
    return {
        "port_number": port,
        "tcp": bool(entry.get("tcp", True)),
        "udp": bool(entry.get("udp", False)),
        "ipv4": bool(entry.get("ipv4", True)),
        "ipv6": bool(entry.get("ipv6", True)),
    }


def apply_firewall_role(session: Session, definition: Dict[str, Any]) -> None:
    """Materialise a ``firewall_role`` policy into the local firewall tables.

    Upserts the role by name and REPLACES its open-port set so the local
    role is an exact mirror of the coordinator's definition (idempotent:
    re-applying the same definition is a no-op net of timestamps).
    Materialising the role does not assign it to any host — assignment
    stays a separate, explicit, queued operation.
    """
    name = (definition.get("name") or "").strip()
    if not name:
        raise PolicyApplyError("firewall_role policy requires a 'name'")
    ports = [_coerce_port(p) for p in definition.get("open_ports", [])]

    role = (
        session.query(models.FirewallRole)
        .filter(models.FirewallRole.name == name)
        .first()
    )
    if role is None:
        role = models.FirewallRole(name=name)
        session.add(role)
        session.flush()
    else:
        # Replace the port set wholesale (cascade delete-orphan drops the old).
        role.open_ports.clear()
        session.flush()

    for spec in ports:
        session.add(
            models.FirewallRoleOpenPort(
                firewall_role_id=role.id,
                port_number=spec["port_number"],
                tcp=spec["tcp"],
                udp=spec["udp"],
                ipv4=spec["ipv4"],
                ipv6=spec["ipv6"],
            )
        )


register_applier("firewall_role", apply_firewall_role)


# ---------------------------------------------------------------------
# update_profile applier
# ---------------------------------------------------------------------


def apply_update_profile(session: Session, definition: Dict[str, Any]) -> None:
    """Materialise an ``update_profile`` policy into the local
    ``upgrade_profiles`` table (a named, schedulable update plan).

    Upserts by name so a centrally-defined patch policy becomes a real
    local UpgradeProfile, exactly as if an operator had created it.
    Materialising does not run it — execution stays on the profile's own
    cron / a separate queued operation.  ``package_managers`` accepts a
    list or a comma-separated string (NULL/empty ⇒ all managers).
    """
    name = (definition.get("name") or "").strip()
    if not name:
        raise PolicyApplyError("update_profile policy requires a 'name'")

    pkg = definition.get("package_managers")
    if isinstance(pkg, (list, tuple)):
        pkg = ",".join(str(p).strip() for p in pkg if str(p).strip()) or None
    elif isinstance(pkg, str):
        pkg = pkg.strip() or None
    else:
        pkg = None

    profile = (
        session.query(models.UpgradeProfile)
        .filter(models.UpgradeProfile.name == name)
        .first()
    )
    if profile is None:
        profile = models.UpgradeProfile(name=name)
        session.add(profile)

    profile.description = definition.get("description")
    if definition.get("cron"):
        profile.cron = str(definition["cron"])
    profile.enabled = bool(definition.get("enabled", True))
    profile.security_only = bool(definition.get("security_only", False))
    profile.package_managers = pkg
    profile.staggered_window_min = int(definition.get("staggered_window_min", 0))


register_applier("update_profile", apply_update_profile)


# ---------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------


def apply_pending_policies(session: Session, *, limit: int = 100) -> Dict[str, Any]:
    """Drain unapplied received-policies and materialise each locally.

    Best-effort per policy: a failure on one (bad definition, missing
    applier) records a structured ``apply_error`` and leaves the row
    ``applied=False`` for retry, without blocking the rest.  Returns
    ``{"applied": n, "failed": n}``.
    """
    rows = inbox_svc.list_unapplied_policies(session)[:limit]
    summary = {"applied": 0, "failed": 0}
    for policy in rows:
        # Capture identifiers up front: a rollback below expires the ORM
        # object, and re-reading attributes off it then would re-load
        # from the DB mid-error-path.
        policy_id = policy.policy_id
        policy_type = policy.policy_type
        definition_json = policy.definition_json

        applier = _APPLIERS.get(policy_type)
        if applier is None:
            inbox_svc.mark_policy_apply_failed(
                session,
                policy_id,
                error=f"no local applier registered for policy_type "
                f"'{policy_type}'",
            )
            session.commit()
            summary["failed"] += 1
            continue
        try:
            definition = json.loads(definition_json or "{}")
            if not isinstance(definition, dict):
                raise PolicyApplyError("definition must be a JSON object")
            applier(session, definition)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Roll back this policy's partial writes, then record the
            # error in its own transaction.  Already-committed policies
            # from earlier in this tick are unaffected.
            session.rollback()
            inbox_svc.mark_policy_apply_failed(session, policy_id, error=str(exc))
            session.commit()
            summary["failed"] += 1
            logger.warning(
                "Failed to apply federation policy %s (%s): %s",
                policy_id,
                policy_type,
                exc,
            )
            continue
        inbox_svc.mark_policy_applied(session, policy_id)
        session.commit()
        summary["applied"] += 1

    logger.info(
        "Federation policy apply: %s applied, %s failed",
        summary["applied"],
        summary["failed"],
    )
    return summary


def supported_policy_types() -> List[str]:
    """Policy types with a registered local applier (for diagnostics)."""
    return sorted(_APPLIERS.keys())
