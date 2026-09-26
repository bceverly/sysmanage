# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Remediation the advisor PROPOSES, and what an approval does (ROADMAP 21.2 S5).

A rule may carry a ``fix`` (see ``advisor_engine``'s fix.pxi): bind to a named
config profile, or generate an ansible-core package upgrade from the rows
that fired it. The engine builds the fix during evaluation; this module keeps
one proposal per (host, rule) in step with it and carries out an approval.

NOTHING IS APPLIED WITHOUT AN OPERATOR
--------------------------------------
The tick only ever creates, refreshes or withdraws ``proposed`` rows. An
approval is the one path to the host, and it is the EXISTING path:
``config_mgmt_remediation.apply_remediation`` -- the same parameter builder,
``queue_apply`` (one uuid for envelope and queue row), the Phase 19
capability refusal and the Phase 14.2 maintenance-window hold at
``outbound_processor``. A generated fix is stored as a real ``ConfigProfile``
first, so its versioning and run history are the ordinary ones.

ASKED ONCE PER FIX, NOT PER TICK
--------------------------------
``fingerprint`` identifies the fix. An operator who rejected "upgrade
openssl" is not asked again every fifteen minutes about the same upgrade; a
changed fix (a new package joins the list) is a new question. A proposal is
WITHDRAWN when its rule stops firing -- not when the rule merely cannot be
assessed, which says nothing about whether the problem went away.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.services import config_mgmt_remediation as remediation

logger = logging.getLogger(__name__)

PROPOSED = models.ADVISOR_PROPOSAL_PROPOSED
APPROVED = models.ADVISOR_PROPOSAL_APPROVED
REJECTED = models.ADVISOR_PROPOSAL_REJECTED
WITHDRAWN = models.ADVISOR_PROPOSAL_WITHDRAWN
FAILED = models.ADVISOR_PROPOSAL_FAILED
# Outcomes that say the problem is GONE. not_assessable is not one of them.
_CLEARED = (models.ADVISOR_OUTCOME_DOES_NOT_FIRE, models.ADVISOR_OUTCOME_NOT_APPLICABLE)

# Reason codes (the UI owns the wording).
REASON_NO_LONGER_FIRES = "no_longer_fires"
REASON_RULE_REMOVED = "rule_removed"
REASON_PROFILE_MISSING = "profile_missing"
REASON_NOT_QUEUED = "not_queued"


class ProposalError(Exception):
    """An approval that cannot proceed; ``code`` says why."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fingerprint(fix: Dict[str, Any]) -> str:
    """Identity of a fix: what it binds to, or exactly what it would run."""
    body = (
        "profile:" + str(fix.get("profile"))
        if fix.get("kind") == "profile"
        else "generate:" + str(fix.get("content"))
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _latest(db, host_id, source: str, key: str):
    return (
        db.query(models.AdvisorProposal)
        .filter(
            models.AdvisorProposal.host_id == host_id,
            models.AdvisorProposal.rule_source == source,
            models.AdvisorProposal.rule_key == key,
        )
        .order_by(models.AdvisorProposal.created_at.desc())
        .first()
    )


def _fill(row, fix: Dict[str, Any], fp: str) -> None:
    row.kind = fix.get("kind")
    row.profile_name = fix.get("profile")
    row.engine = fix.get("engine")
    row.content = fix.get("content")
    row.packages = fix.get("packages")
    row.skipped = fix.get("skipped") or 0
    row.fingerprint = fp


def sync(db, host_id, entry: Dict[str, Any], result: Dict[str, Any], summary) -> None:
    """Keep this (host, rule)'s proposal in step with its latest outcome."""
    latest = _latest(db, host_id, entry["source"], entry["key"])
    fix = result.get("fix")
    if result.get("outcome") == models.ADVISOR_OUTCOME_FIRES and fix:
        fp = fingerprint(fix)
        if latest is not None and latest.status == PROPOSED:
            if latest.fingerprint != fp:
                _fill(latest, fix, fp)
                latest.updated_at = _now()
            return
        if latest is not None and latest.fingerprint == fp:
            return  # the operator already decided on this exact fix
        row = models.AdvisorProposal(
            id=uuid.uuid4(),
            host_id=host_id,
            rule_source=entry["source"],
            rule_key=entry["key"],
            shared_rule_id=entry.get("shared_rule_id"),
            rule_id=entry.get("rule_id"),
            status=PROPOSED,
            created_at=_now(),
            updated_at=_now(),
        )
        _fill(row, fix, fp)
        db.add(row)
        summary["proposals_opened"] = summary.get("proposals_opened", 0) + 1
    elif result.get("outcome") in _CLEARED and latest is not None:
        if latest.status == PROPOSED:
            latest.status = WITHDRAWN
            latest.reason = REASON_NO_LONGER_FIRES
            latest.updated_at = _now()


def withdraw_for(db, source: str, key: str) -> None:
    """A rule was removed: its open proposals are withdrawn, not left dangling."""
    for row in db.query(models.AdvisorProposal).filter(
        models.AdvisorProposal.rule_source == source,
        models.AdvisorProposal.rule_key == key,
        models.AdvisorProposal.status == PROPOSED,
    ):
        row.status = WITHDRAWN
        row.reason = REASON_RULE_REMOVED
        row.updated_at = _now()


def _profile_for(db, proposal, userid: str):
    """The ConfigProfile this approval applies -- creating it for a generated fix."""
    if proposal.kind == "profile":
        profile = (
            db.query(models.ConfigProfile)
            .filter(models.ConfigProfile.name == proposal.profile_name)
            .first()
        )
        if profile is None or not profile.is_active:
            raise ProposalError(REASON_PROFILE_MISSING)
        return profile
    host = db.get(models.Host, proposal.host_id)
    now = _now()
    profile = models.ConfigProfile(
        id=uuid.uuid4(),
        name=f"advisor-fix {proposal.rule_key} {host.fqdn} {proposal.id.hex[:8]}"[:255],
        description=f"Generated by the advisor for {proposal.rule_key} on {host.fqdn}",
        engine=proposal.engine,
        content=proposal.content,
        version=1,
        is_active=True,
        created_by=userid,
        updated_by=userid,
        created_at=now,
        updated_at=now,
    )
    db.add(profile)
    db.flush()
    return profile


def approve(db, proposal, userid: str):
    """Apply an approved proposal through the ordinary path. Records the
    decision either way; raises ProposalError when it cannot be queued."""
    if proposal.status != PROPOSED:
        raise ProposalError("not_proposed")
    proposal.decided_by = userid
    proposal.decided_at = _now()
    host = db.get(models.Host, proposal.host_id)
    try:
        # One savepoint for BOTH: a fix that cannot be queued must not leave
        # its generated profile behind as an orphan in the profile library.
        with db.begin_nested():
            profile = _profile_for(db, proposal, userid)
            proposal.command_id = remediation.apply_remediation(db, host, profile)
    except ProposalError as exc:
        proposal.status, proposal.reason = FAILED, exc.code
        raise
    except Exception as exc:  # pylint: disable=broad-except
        # Includes a host that has not advertised config-management support.
        logger.warning(
            "Advisor proposal %s for host %s could not be queued: %s",
            proposal.id,
            host.fqdn if host else proposal.host_id,
            exc,
        )
        proposal.status, proposal.reason = FAILED, REASON_NOT_QUEUED
        raise ProposalError(REASON_NOT_QUEUED) from exc
    proposal.status = APPROVED
    proposal.profile_id = profile.id
    return proposal


def reject(proposal, userid: str):
    if proposal.status != PROPOSED:
        raise ProposalError("not_proposed")
    proposal.status = REJECTED
    proposal.decided_by = userid
    proposal.decided_at = _now()
    return proposal


def proposal_dict(db, row, fqdn: Optional[str] = None) -> Dict[str, Any]:
    """A proposal as the API shows it, with the run its approval produced."""
    run = None
    if row.command_id:
        found = (
            db.query(models.ConfigProfileRun)
            .filter(models.ConfigProfileRun.command_id == row.command_id)
            .first()
        )
        if found is not None:
            run = {
                "success": bool(found.success),
                "completed_at": (
                    found.completed_at.isoformat() if found.completed_at else None
                ),
            }
    return {
        "id": str(row.id),
        "host_id": str(row.host_id),
        "fqdn": fqdn,
        "source": row.rule_source,
        "key": row.rule_key,
        "kind": row.kind,
        "profile_name": row.profile_name,
        "engine": row.engine,
        "content": row.content,
        "packages": row.packages or [],
        "skipped": row.skipped,
        "status": row.status,
        "reason": row.reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "profile_id": str(row.profile_id) if row.profile_id else None,
        "command_id": row.command_id,
        # None until the agent answers -- a queued fix held by a maintenance
        # window is "approved, not yet run", never "applied".
        "run": run,
    }
