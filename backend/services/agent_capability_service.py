# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Ingest and query agent capability advertisements — ROADMAP Phase 19.

WHERE "LIMITED" COMES FROM
--------------------------
Not from a baseline list kept on the server.  The obvious design — hold the
full capability set here and flag anything smaller — needs a constant that
mirrors the agent's taxonomy across two repositories, and that drifts the
first time the agent gains a capability the server has not heard of: every
up-to-date host would be flagged limited by a stale server.

The agent already knows what it is missing.  It derives its report from its own
command-handler map against its own taxonomy, so ``unavailable`` and
``partial`` are exactly "what this build cannot do relative to a full one".
A host is limited when either is non-empty.  No server-side baseline, nothing
to keep in sync, and a newer agent advertising capabilities this server has
never seen is simply not limited — which is correct.

WHY UNKNOWN IS NOT LIMITED
--------------------------
``agent_capabilities IS NULL`` means the host never told us: an older agent, or
one whose report could not be built.  That is a THIRD state, not a synonym for
limited.  Flagging it limited would light up every pre-upgrade host in the
fleet, and — worse — gating dispatch on it would break working hosts.  Unknown
hosts are therefore never flagged and never gated.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.i18n import _
from backend.utils.log_sanitize import scrub

logger = logging.getLogger(__name__)

# Bumping this is the server's opt-in to a NEW report shape.  A report claiming
# a shape we do not implement is rejected rather than half-read: a partially
# understood capability set is indistinguishable from a limited agent, and
# would silently gate commands the host can actually run.
MAX_SUPPORTED_SCHEMA_VERSION = 1


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_report(report: Any) -> Optional[Dict[str, Any]]:
    """Validate an advertisement and reduce it to the fields we store.

    Returns ``None`` when the report is unusable — malformed, or a schema
    version this server does not implement.  Unknown KEYS inside a supported
    version are dropped rather than rejected, so a newer agent can add fields
    without breaking ingestion here (the same contract federation uses for a
    site's ``capabilities`` metadata).
    """
    if not isinstance(report, dict):
        return None

    version = report.get("schema_version")
    if not isinstance(version, int) or version < 1:
        logger.warning("agent capability report has no usable schema_version")
        return None
    if version > MAX_SUPPORTED_SCHEMA_VERSION:
        # Loud: this is a deployment problem (agent newer than server), and
        # silently ignoring it would present the host as unknown-capability
        # forever with no clue why.
        logger.warning(
            "agent advertises capability schema v%s but this server implements "
            "v%s — ignoring the report; upgrade the server to consume it",
            # Scrubbed because it came out of the agent's report: the isinstance
            # guard above already proves it is an int, but the rule is "every
            # value off the wire goes through scrub" and an exception to that
            # rule is what makes the next one easy to miss.
            scrub(version),
            MAX_SUPPORTED_SCHEMA_VERSION,
        )
        return None

    def _str_list(value):
        if not isinstance(value, list):
            return []
        return sorted({str(v) for v in value if isinstance(v, (str, int))})

    def _str_map(value):
        if not isinstance(value, dict):
            return {}
        return {str(k): v for k, v in sorted(value.items())}

    commands = _str_list(report.get("commands"))
    if not commands:
        # A report with no routable commands is not a limited agent, it is a
        # broken report — an agent that can run nothing could not have sent it.
        logger.warning("agent capability report lists no commands; ignoring")
        return None

    return {
        "schema_version": version,
        "capabilities": _str_list(report.get("capabilities")),
        "commands": commands,
        "unavailable": _str_map(report.get("unavailable")),
        "partial": _str_map(report.get("partial")),
    }


def limited_flag(host) -> Optional[bool]:
    """Three-valued 'is this agent limited?' for API responses.

    ``True`` limited, ``False`` full, ``None`` NEVER ADVERTISED.  The third is
    the one that needs saying out loud: ``bool(host.agent_capabilities_limited)``
    collapses a NULL column to ``False``, which presents every agent that has
    not upgraded as full-capability — a claim the server cannot make.  That bug
    was written and caught during Phase 19; this exists so the conversion has
    ONE definition rather than a copy in each serializer.
    """
    if not getattr(host, "agent_capabilities", None):
        return None
    return bool(getattr(host, "agent_capabilities_limited", False))


def capability_update_values(report: Any) -> Dict[str, Any]:
    """The ``Host`` column updates for an advertisement, as a plain dict.

    The SYSTEM_INFO handler builds an UPDATE payload rather than mutating an ORM
    object, so it needs the same decision in dict form.  Both shapes go through
    here so the "limited" rule has exactly one definition — deriving it twice is
    how the two would drift.

    Returns ``{}`` when the report is unusable, which callers can ``update()``
    unconditionally: an empty dict leaves any previous advertisement intact.
    """
    normalized = normalize_report(report)
    if normalized is None:
        return {}
    return {
        "agent_capabilities": json.dumps(normalized, sort_keys=True),
        "agent_capabilities_limited": bool(
            normalized["unavailable"] or normalized["partial"]
        ),
        "agent_capabilities_updated_at": _utcnow_naive(),
    }


def apply_capability_report(host, report: Any) -> bool:
    """Persist a capability advertisement onto ``host``.

    Returns True when the host was updated.  An unusable report leaves any
    PREVIOUS advertisement in place: a bad message should not erase what we
    already knew, which would flip a host to unknown and silently un-gate it.
    """
    values = capability_update_values(report)
    if not values:
        return False
    for column, value in values.items():
        setattr(host, column, value)
    return True


def get_capability_report(host) -> Optional[Dict[str, Any]]:
    """The stored advertisement, or None when the host never sent a usable one."""
    raw = getattr(host, "agent_capabilities", None)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("stored agent_capabilities for a host is not valid JSON")
        return None
    return parsed if isinstance(parsed, dict) else None


def host_supports(host, command_type: str) -> Optional[bool]:
    """Can this host run ``command_type``?

    Three-valued ON PURPOSE:

    * ``True``  — advertised; dispatch it.
    * ``False`` — the host told us it cannot route this; refuse with a clear
      message instead of letting it fail at runtime.
    * ``None``  — unknown (older agent, or never advertised).  The caller MUST
      dispatch anyway.  Treating unknown as unsupported would break every host
      that has not yet upgraded, which is the opposite of the point.
    """
    report = get_capability_report(host)
    if not report:
        return None
    commands = report.get("commands")
    if not isinstance(commands, list) or not commands:
        return None
    return str(command_type) in commands


class UnsupportedCapabilityError(Exception):
    """A command was addressed to a host whose agent cannot route it.

    Raised at ENQUEUE time, not at delivery: the point of advertisement is to
    fail before the message is written to the host's queue, so the operator
    gets an immediate, accurate answer instead of a command that sits pending
    and then comes back "Unknown command type" minutes later.
    """

    def __init__(self, command_type: str, hostname: Optional[str] = None):
        self.command_type = command_type
        self.hostname = hostname
        target = hostname or _("this host")
        super().__init__(
            _(
                "The agent on {host} does not support '{command}'. It advertises "
                "a reduced capability set, so the command was not sent."
            ).format(host=target, command=command_type)
        )


def assert_host_supports(host, command_type: Optional[str]) -> None:
    """Refuse a command the host has told us it cannot run.

    Deliberately permissive in two cases, because a false refusal is worse
    than a late failure:

    * ``command_type`` missing — not a routed command; nothing to check.
    * capability UNKNOWN (older agent) — dispatch anyway.  Gating unknown
      hosts would break every agent that has not yet upgraded.

    Only an explicit "I cannot route this" is refused.
    """
    if not command_type:
        return
    if host_supports(host, command_type) is False:
        raise UnsupportedCapabilityError(str(command_type), getattr(host, "fqdn", None))
