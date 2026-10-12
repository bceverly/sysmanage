# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The fleet NTP policy (Phase 23.3 S5b; the rules are Pro+).

Which NTP servers hosts should use: one policy for the fleet, overridable per
site and tag (an air-gapped site's internal pair).  ``compliance`` compares
each host's reported configuration with its policy, field by field, through
``config_management_engine``; ``reconcile`` APPLIES an enforced policy -- the
engine builds a plan for the time service the host really runs, sent through
the agent's generic ``apply_deployment_plan`` -- and, where the policy says
so, resyncs a clock that breached its bounds.

Like antivirus auto-deploy (21.3): done means the agent said the plan
SUCCEEDED (``record_result``, by command id); a failure is retried with
backoff and never given up; a changed policy (or a host whose service
changed) is sent again; a host that drifts back after a successful apply is
re-applied, no more than once per ``REAPPLY_AFTER``.  At most
``MAX_PUSHES_PER_PASS`` plans per database per pass, so a new fleet policy
reaches hosts in waves.

Without the engine nothing is judged and nothing applied: "no policy engine"
is said, never "compliant".
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.persistence import models
from backend.services import clock_resync, clock_status, config_mgmt_spec_shim

logger = logging.getLogger(__name__)

SCOPE_FLEET = "fleet"
SCOPE_SITE = "site"
SCOPE_TAG = "tag"
SCOPES = (SCOPE_FLEET, SCOPE_SITE, SCOPE_TAG)

# Bumped when the engine's plans change, so every host gets the new one.
PLAN_VERSION = 1
MAX_PUSHES_PER_PASS = 100
RETRY_BASE = timedelta(hours=1)
RETRY_MAX = timedelta(hours=24)
REAPPLY_AFTER = timedelta(hours=1)
AUTO_RESYNC_COOLDOWN = timedelta(hours=1)
TICK_SECONDS = 60.0
ERROR_BACKOFF_SECONDS = 120.0
SYSTEM_ACTOR = "system:ntp-policy"

IDLE = "idle"  # nothing sent yet
QUEUED = "queued"
SUCCEEDED = "succeeded"
FAILED = "failed"

# Findings a plan can fix; the others need a person (no time service, an
# agent too old to report its configuration).
_FIXABLE = {"servers_differ", "not_enabled", "not_running"}
_PLATFORMS = {"macOS": "Darwin"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def engine():
    """The policy engine (``config_management_engine``), or None."""
    module = config_mgmt_spec_shim.engine_module()
    return module if module is not None and hasattr(module, "ntp_compare") else None


def servers_of(policy) -> List[str]:
    try:
        value = json.loads(policy.servers or "[]")
    except ValueError:
        return []
    return [s for s in value if isinstance(s, str)] if isinstance(value, list) else []


def host_view(host) -> Dict[str, Any]:
    """The host as the engine reads it."""
    from backend.api.handlers.time_status_handlers import (  # noqa: PLC0415
        configured_servers,
    )

    return {
        "system": _PLATFORMS.get(host.platform, host.platform),
        "service": host.time_service,
        "unit": host.time_service_unit,
        "config_path": host.time_config_path,
        "configured_servers": configured_servers(host),
        "enabled": host.time_service_enabled,
        "running": host.time_service_running,
    }


class Resolver:
    """Which policy applies to each host, from one read of the policies."""

    def __init__(self, db):
        self.fleet = None
        self.sites: Dict[str, Any] = {}
        self.tags: Dict[str, Any] = {}
        for row in db.query(models.NtpPolicy).all():
            if row.scope_kind == SCOPE_FLEET:
                self.fleet = row
            elif row.scope_kind == SCOPE_SITE:
                self.sites[row.scope_ref] = row
            elif row.scope_kind == SCOPE_TAG:
                self.tags[row.scope_ref] = row
        self.host_tags: Dict[str, List[str]] = {}
        if self.tags:
            for host_id, tag_id in db.query(
                models.HostTag.host_id, models.HostTag.tag_id
            ).filter(models.HostTag.tag_id.in_(list(self.tags))):
                self.host_tags.setdefault(str(host_id), []).append(str(tag_id))

    def policy_for(self, host) -> Tuple[Optional[Any], bool]:
        """``(policy, conflict)``.  Two tag policies with different servers
        are a conflict: reported, applied by neither."""
        tagged = [self.tags[t] for t in self.host_tags.get(str(host.id), ())]
        if tagged:
            distinct = {tuple(sorted(s.lower() for s in servers_of(p))) for p in tagged}
            if len(distinct) > 1:
                return None, True
            return tagged[0], False
        site = self.sites.get(str(host.site_id)) if host.site_id else None
        return site or self.fleet, False


def digest(policy, view: Dict[str, Any]) -> str:
    """What was sent: the servers, and the service it was built for."""
    material = json.dumps(
        [
            PLAN_VERSION,
            sorted(servers_of(policy)),
            view["service"],
            view["unit"],
            view["config_path"],
            view["system"],
        ],
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def evaluate(db, hosts: Iterable) -> Dict[str, Dict[str, Any]]:
    """Per host id: ``{policy, conflict, findings, compliant}``.  Empty when
    there is no engine (nothing is judged without the rules)."""
    module = engine()
    if module is None:
        return {}
    resolver = Resolver(db)
    out: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        policy, conflict = resolver.policy_for(host)
        if conflict:
            findings = [{"code": "policy_conflict"}]
        elif policy is None:
            findings = []
        else:
            findings = list(module.ntp_compare(host_view(host), servers_of(policy)))
        out[str(host.id)] = {
            "policy": policy,
            "conflict": conflict,
            "findings": findings,
            "compliant": None if policy is None and not conflict else not findings,
        }
    return out


def _retry_delay(attempts: int) -> timedelta:
    return min(RETRY_BASE * (2 ** max(attempts - 1, 0)), RETRY_MAX)


def _due(state, wanted: str, now: datetime) -> bool:
    if state is None or state.policy_digest != wanted:
        return True
    if state.status == FAILED:
        return (state.finished_at or now) + _retry_delay(state.attempts) <= now
    if state.status == QUEUED:
        return (state.sent_at or now) + RETRY_MAX <= now  # never answered
    # Succeeded, yet the host reports a difference again: it drifted back.
    return (state.finished_at or now) + REAPPLY_AFTER <= now


def _state(db, states, host):
    state = states.get(str(host.id))
    if state is None:
        state = models.NtpPolicyState(host_id=host.id, status=IDLE, attempts=0)
        db.add(state)
        states[str(host.id)] = state
    return state


def _push(db, module, host, policy, view, state, now) -> Optional[str]:
    built = module.ntp_build_plan(view, servers_of(policy))
    if "plan" not in built:
        return None
    from backend.services.config_mgmt_dispatch import queue_command  # noqa: PLC0415
    from backend.websocket.messages import CommandType  # noqa: PLC0415

    try:
        state.command_id = queue_command(
            db, host.id, CommandType.APPLY_DEPLOYMENT_PLAN, {"plan": built["plan"]}
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("NTP policy: could not queue the plan for host %s", host.id)
        return None
    state.policy_digest = digest(policy, view)
    state.status, state.sent_at, state.finished_at = QUEUED, now, None
    state.attempts = (state.attempts or 0) + 1
    return state.command_id


def _auto_resync(db, host, status, state, now) -> bool:
    if status not in (clock_status.STATUS_WARNING, clock_status.STATUS_CRITICAL):
        return False
    if state.auto_resync_at and state.auto_resync_at + AUTO_RESYNC_COOLDOWN > now:
        return False
    rows, _skipped = clock_resync.request(db, [host], SYSTEM_ACTOR)
    state.auto_resync_at = now
    return bool(rows)


def reconcile(db, now: Optional[datetime] = None) -> Dict[str, int]:
    """Apply enforced policies and auto-resync breaching clocks.  Commits."""
    now = now or _now()
    summary = {"pushed": 0, "resynced": 0}
    module = engine()
    if module is None or not db.query(models.NtpPolicy).count():
        return summary
    hosts = (
        db.query(models.Host)
        .filter(models.Host.approval_status == "approved", models.Host.active.is_(True))
        .all()
    )
    judged = evaluate(db, hosts)
    states = {str(s.host_id): s for s in db.query(models.NtpPolicyState)}
    _server, clocks = clock_status.evaluate(db, hosts, now)
    clock_by_host = {str(h.id): st for h, _b, st in clocks}
    for host in hosts:
        verdict = judged.get(str(host.id)) or {}
        policy = verdict.get("policy")
        if policy is None or not host.is_agent_privileged:
            continue
        if policy.auto_resync and _auto_resync(
            db, host, clock_by_host.get(str(host.id)), _state(db, states, host), now
        ):
            summary["resynced"] += 1
        fixable = {f["code"] for f in verdict["findings"]} & _FIXABLE
        if (
            not policy.enforce
            or not fixable
            or summary["pushed"] >= MAX_PUSHES_PER_PASS
        ):
            continue
        view = host_view(host)
        state = _state(db, states, host)
        if _due(state, digest(policy, view), now) and _push(
            db, module, host, policy, view, state, now
        ):
            summary["pushed"] += 1
    db.commit()
    if summary["pushed"]:
        logger.info("NTP policy: sent %d plan(s)", summary["pushed"])
    return summary


def record_result(db, message_data: Dict[str, Any]) -> bool:
    """Close the policy apply this ``apply_deployment_plan`` result answers;
    False for any other plan.  The caller commits."""
    command_id = message_data.get("command_id")
    if not command_id:
        return False
    state = (
        db.query(models.NtpPolicyState)
        .filter(models.NtpPolicyState.command_id == str(command_id))
        .first()
    )
    if state is None:
        return False
    result = message_data.get("result")
    ok = bool(message_data.get("success")) and not (
        isinstance(result, dict) and result.get("success") is False
    )
    state.finished_at = _now()
    if ok:
        state.status, state.last_error = SUCCEEDED, None
        return True
    errors = result.get("errors") if isinstance(result, dict) else None
    text = (
        "; ".join(str(e) for e in errors)
        if errors
        else str(message_data.get("error") or "the agent reported failure")
    )
    state.status, state.last_error = FAILED, text[:2000]
    logger.warning(
        "NTP policy: plan FAILED on host %s (attempt %d): %s",
        state.host_id,
        state.attempts,
        state.last_error,
    )
    return True


def run_one_tick() -> Dict[str, int]:
    """Reconcile every host database.  Never raises."""
    from backend.persistence.partitions import (  # noqa: PLC0415
        iter_host_databases,
    )

    total = {"pushed": 0, "resynced": 0}
    if engine() is None:
        return total
    for label, _tenant, db_session in iter_host_databases():
        try:
            for key, value in reconcile(db_session).items():
                total[key] += value
        except Exception:  # pylint: disable=broad-exception-caught
            db_session.rollback()
            logger.exception("NTP policy tick failed for database %s", label)
        finally:
            db_session.close()
    return total


async def ntp_policy_tick_service() -> None:
    from backend.startup.tick_runner import run_periodic  # noqa: PLC0415

    await run_periodic(
        "NTP policy tick",
        run_one_tick,
        TICK_SECONDS,
        ERROR_BACKOFF_SECONDS,
        logger=logger,
    )


def as_dict(policy) -> Dict[str, Any]:
    return {
        "id": str(policy.id),
        "scope_kind": policy.scope_kind,
        "scope_ref": policy.scope_ref,
        "servers": servers_of(policy),
        "enforce": bool(policy.enforce),
        "auto_resync": bool(policy.auto_resync),
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        "updated_by": policy.updated_by,
    }


def set_policy(db, scope_kind, scope_ref, servers, enforce, auto_resync, user):
    row = (
        db.query(models.NtpPolicy)
        .filter(
            models.NtpPolicy.scope_kind == scope_kind,
            models.NtpPolicy.scope_ref == scope_ref,
        )
        .first()
    )
    if row is None:
        row = models.NtpPolicy(
            id=uuid.uuid4(), scope_kind=scope_kind, scope_ref=scope_ref
        )
        db.add(row)
    row.servers = json.dumps(list(servers))
    row.enforce, row.auto_resync = bool(enforce), bool(auto_resync)
    row.updated_at, row.updated_by = _now(), user
    db.commit()
    return row


def clear_policy(db, scope_kind, scope_ref) -> bool:
    deleted = (
        db.query(models.NtpPolicy)
        .filter(
            models.NtpPolicy.scope_kind == scope_kind,
            models.NtpPolicy.scope_ref == scope_ref,
        )
        .delete()
    )
    db.commit()
    return bool(deleted)
