# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Restore readiness (ROADMAP 27.1, Enterprise ``backup_ops_engine``).

For each backup policy: is the last good backup within its recovery point
objective, how long would getting it back take (RTO, from the best
throughput the host has shown), and has the repository been proven readable
recently?  A host whose proof is stale shows "unproven" however recent its
backups are.

This module gathers the facts -- the runs are tenant data -- as plain data
and the engine decides what they mean (``assess_readiness``).  Without the
engine the API answers 402; nothing here changes how backups run.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_verify

ENGINE = "backup_ops_engine"
# How many recent runs of each kind are offered as throughput evidence.
RECENT = 5


def engine():
    """The loaded engine, or None (unlicensed: the API answers 402)."""
    eng = module_loader.get_module(ENGINE)
    return eng if hasattr(eng, "assess_readiness") else None


def _result(run: models.BackupRun) -> Dict[str, Any]:
    try:
        found = json.loads(run.result) if run.result else {}
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _ended(run: models.BackupRun) -> Optional[datetime]:
    return run.finished_at or run.queued_at


def _recent(db: Session, policy, action: str) -> List[models.BackupRun]:
    return (
        db.query(models.BackupRun)
        .filter(
            models.BackupRun.policy_id == policy.id,
            models.BackupRun.action == action,
            models.BackupRun.status == "ok",
        )
        .order_by(models.BackupRun.queued_at.desc())
        .limit(RECENT)
        .all()
    )


def _rate(kind: str, run, num_bytes, seconds) -> Optional[Dict[str, Any]]:
    if not isinstance(num_bytes, int) or not isinstance(seconds, (int, float)):
        return None
    return {"kind": kind, "bytes": num_bytes, "seconds": seconds, "at": _ended(run)}


def _throughputs(db: Session, policy) -> List[Dict[str, Any]]:
    """What the host has shown it can read back: restores (their bytes),
    full-read verifications (every byte of the repository) and captures
    (what they read) -- the engine picks the most trustworthy."""
    found: List[Optional[Dict[str, Any]]] = []
    for run in _recent(db, policy, jobs.RESTORE):
        result = _result(run)
        restore = result.get("restore") or {}
        found.append(_rate("restore", run, restore.get("bytes"), result.get("seconds")))
    for run in _recent(db, policy, jobs.VERIFY):
        result = _result(run)
        check = result.get("check") or {}
        found.append(_rate("verify", run, check.get("bytes"), result.get("seconds")))
    for run in _recent(db, policy, "capture"):
        result = _result(run)
        found.append(
            _rate("capture", run, result.get("read_bytes"), result.get("seconds"))
        )
    return [rate for rate in found if rate is not None]


def _snapshot_bytes(capture: Optional[models.BackupRun]) -> Optional[int]:
    """The latest good snapshot's size: what it reused plus what it added."""
    if capture is None:
        return None
    result = _result(capture)
    total = (result.get("reused_bytes") or 0) + (result.get("new_bytes") or 0)
    return total or None


def facts(db: Session, policy: models.BackupPolicy) -> Dict[str, Any]:
    """Everything the engine needs about one policy, as plain data."""
    good = jobs.latest_run(db, policy.id, "capture", statuses=jobs.GOOD_CAPTURE)
    proof = backup_verify.last_good(db, policy)
    evidence = []
    if proof is not None:
        evidence.append(
            {
                "kind": "verify",
                "passed_at": _ended(proof),
                # A pass is good proof for its own cadence (Pro+ 24.6).
                "max_age_days": backup_verify.interval(policy) or None,
            }
        )
    return {
        "interval_hours": policy.interval_hours,
        "rpo_hours": policy.rpo_hours,
        "last_good_at": _ended(good) if good is not None else None,
        "snapshot_bytes": _snapshot_bytes(good),
        "evidence": evidence,
        "throughputs": _throughputs(db, policy),
    }


def _iso(when: Any) -> Any:
    return when.isoformat() if isinstance(when, datetime) else when


def fleet(db: Session, eng, now: datetime) -> Dict[str, Any]:
    """Every policy's readiness, worst first, with counts by state."""
    rows = []
    policies = (
        db.query(models.BackupPolicy, models.Host)
        .join(models.Host, models.Host.id == models.BackupPolicy.host_id)
        .filter(models.Host.approval_status == "approved")
        .all()
    )
    for policy, host in policies:
        verdict = eng.assess_readiness(facts(db, policy), now)
        proof = verdict.get("proof")
        if proof:
            proof = {**proof, "at": _iso(proof.get("at"))}
        rows.append(
            {
                "host_id": str(host.id),
                "fqdn": host.fqdn,
                "policy_id": str(policy.id),
                "enabled": bool(policy.enabled),
                **verdict,
                "proof": proof,
            }
        )
    order = {"never_backed_up": 0, "rpo_breached": 1, "unproven": 2, "ready": 3}
    rows.sort(key=lambda row: (order.get(row["state"], 9), row["fqdn"]))
    return {"hosts": rows, "counts": eng.summarize_readiness(rows)}
