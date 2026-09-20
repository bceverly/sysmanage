# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remediation playbooks: matching a drift finding to its repair (Phase 20.1).

20.2 shipped remediate-to-baseline, which re-applies the WHOLE profile a host
drifted from. That is the right hammer when the profile is small and the wrong
one when it is a four-hundred-task baseline and the divergence is a single file
mode: the operator wanted a permission fixed and got an hour of unrelated
convergence, during a maintenance window they had budgeted for one change.

A remediation playbook is the narrow alternative. It is a stored
``ConfigProfile`` like any other -- authoring, validation, versioning, the
licensed spec builders, dispatch and run history all reused rather than
re-grown -- bound to the findings it repairs by a ``ConfigRemediationRule``.

WHAT THIS MODULE OWNS AND WHAT IT ASKS
--------------------------------------
It owns loading candidate rules and turning a match into a queued command.
WHICH rule wins is an engine question (``config_remediation.pxi``): precedence
between overlapping rules has to be identical whether an operator pressed a
button or the reconciler fired unattended, and two implementations of that is
how a preview ends up promising something the automatic path does not do.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models
from backend.services import config_mgmt_dispatch as dispatch
from backend.services import config_mgmt_spec_shim as shim

logger = logging.getLogger(__name__)

_NO_ENGINE = "configuration management engine is not available"


def _engine():
    """The Pro+ module, or None when it is not loaded."""
    return shim.engine_module()


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def validate_rule(
    name: str, task_pattern: str, priority: Optional[int] = None
) -> Optional[str]:
    """Ask the engine whether a rule is acceptable."""
    module = _engine()
    if module is None:
        return _NO_ENGINE
    return module.validate_remediation_rule(name, task_pattern, priority)


def _candidate_rules(db_session: Session, auto_only: bool) -> List[Any]:
    """Every enabled rule, for the engine to choose between.

    Loaded wholesale rather than filtered in SQL by pattern, because the
    pattern dialect is the engine's (globs, case-insensitive) and encoding it
    as a LIKE here would be a second, subtly different implementation of the
    matching rule -- the exact thing this split exists to prevent. Rule
    libraries are operator-authored and number in the tens, so the cost is
    nothing; if that ever stops being true, the fix is an engine-supplied
    prefilter, not a LIKE.
    """
    query = db_session.query(models.ConfigRemediationRule).filter(
        models.ConfigRemediationRule.enabled.is_(True)
    )
    if auto_only:
        query = query.filter(models.ConfigRemediationRule.auto_apply.is_(True))
    return query.all()


def match_for_finding(
    db_session: Session, finding, auto_only: bool = False
) -> Tuple[Optional[Any], Optional[Any]]:
    """The rule that repairs this finding and the profile it names.

    Returns ``(rule, remediation_profile)``, either of which may be None: no
    rule matched, or the rule matched but its remediation profile has been
    retired. Those are different answers and the caller reports them
    differently -- "nothing knows how to fix this" sends an operator to write
    a rule, "the fix was turned off" sends them to turn it back on.
    """
    module = _engine()
    if module is None:
        return None, None

    rule = module.match_remediation_rule(
        _candidate_rules(db_session, auto_only),
        finding.profile_id,
        finding.task_name,
        auto_only,
    )
    if rule is None:
        return None, None

    profile = (
        db_session.query(models.ConfigProfile)
        .filter(models.ConfigProfile.id == rule.remediation_profile_id)
        .first()
    )
    if profile is None or not profile.is_active:
        # Loud, because this is a repair somebody wrote down and expects to
        # happen. A rule pointing at a retired profile is silent breakage of
        # exactly the kind auto-apply makes dangerous.
        logger.warning(
            "Remediation rule '%s' matched but its profile %s is missing or "
            "inactive; nothing will be applied",
            rule.name,
            rule.remediation_profile_id,
        )
        return rule, None
    return rule, profile


def preview(rule, task_name: str) -> Optional[Dict[str, Any]]:
    """The engine's own account of a match, for a confirmation dialog.

    Asked of the engine rather than assembled here so the sentence an operator
    confirms is generated from the same place as the decision.
    """
    module = _engine()
    if module is None or rule is None:
        return None
    return module.remediation_preview(rule, task_name)


def apply_remediation(db_session: Session, host, profile, check_mode: bool = False):
    """Queue a remediation profile against one host. Returns the command id.

    Goes through the same builder as every other apply, so a repair cannot
    diverge from what a normal application of that profile would have done,
    and inherits both existing guards without re-implementing either:
    ``enqueue_message`` refuses a host that has not advertised support
    (Phase 19), and ``outbound_processor`` holds delivery outside a
    maintenance window (Phase 14.2).
    """
    parameters = dispatch.parameters_for(profile, check_mode=check_mode)
    return dispatch.queue_apply(db_session, host.id, parameters)


def auto_remediate(db_session: Session, findings: List[Any]) -> Dict[str, int]:
    """Fire unattended repairs for findings that just OPENED. Never raises.

    Only newly-opened findings are passed in, which is what keeps this from
    firing every minute at a divergence the repair cannot fix: a finding that
    is merely still open is not a new event, and a repair that did not work
    should be visible as persistent drift rather than as an infinite loop of
    attempts. A regression re-opens the finding and does earn a fresh attempt,
    which is right -- the host was compliant and has moved again.

    Never raises: this runs inside the result handler's transaction, and a
    remediation problem must not cost us the run row, which is the more
    valuable record of the two.
    """
    summary = {"matched": 0, "queued": 0, "failed": 0}
    if not findings or _engine() is None:
        return summary

    try:
        for finding in findings:
            rule, profile = match_for_finding(db_session, finding, auto_only=True)
            if rule is None or profile is None:
                continue
            summary["matched"] += 1

            host = (
                db_session.query(models.Host)
                .filter(models.Host.id == finding.host_id)
                .first()
            )
            if host is None or not host.active:
                logger.info(
                    "Auto-remediation rule '%s' matched drift on host %s, which "
                    "is inactive or gone; not queued",
                    rule.name,
                    finding.host_id,
                )
                continue

            try:
                apply_remediation(db_session, host, profile)
            except Exception as exc:  # pylint: disable=broad-except
                # Per-host isolation: one host that cannot take the command
                # must not stop the other findings in this batch from being
                # repaired. Logged with everything needed to explain it --
                # which rule, which host, which task, why.
                summary["failed"] += 1
                logger.warning(
                    "Auto-remediation '%s' could not be queued for host %s "
                    "(task %r): %s",
                    rule.name,
                    host.fqdn,
                    finding.task_name,
                    exc,
                )
                continue

            summary["queued"] += 1
            logger.info(
                "Auto-remediation '%s' queued for host %s: profile '%s' repairs "
                "drift on task %r",
                rule.name,
                host.fqdn,
                profile.name,
                finding.task_name,
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Automatic remediation pass failed")

    return summary


def rule_to_dict(row, profile_names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Serialise a remediation rule for the API.

    Both profile names are resolved by the caller and passed in rather than
    lazy-loaded per row: the list view renders every rule, and a relationship
    walked per row is the classic N+1 that only shows up once a customer has a
    real rule library.
    """
    names = profile_names or {}
    scope_id = str(row.profile_id) if row.profile_id else None
    repair_id = str(row.remediation_profile_id)
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "profile_id": scope_id,
        "profile_name": names.get(scope_id) if scope_id else None,
        "task_pattern": row.task_pattern,
        "remediation_profile_id": repair_id,
        "remediation_profile_name": names.get(repair_id),
        "enabled": bool(row.enabled),
        "priority": row.priority,
        "auto_apply": bool(row.auto_apply),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": _utc(row.created_at),
        "updated_at": _utc(row.updated_at),
    }


def profile_names_for(db_session: Session, rows: List[Any]) -> Dict[str, str]:
    """Resolve every profile id a set of rules mentions, in one query."""
    wanted = set()
    for row in rows:
        if row.profile_id:
            wanted.add(row.profile_id)
        if row.remediation_profile_id:
            wanted.add(row.remediation_profile_id)
    if not wanted:
        return {}
    return {
        str(profile.id): profile.name
        for profile in db_session.query(models.ConfigProfile)
        .filter(models.ConfigProfile.id.in_(wanted))
        .all()
    }
