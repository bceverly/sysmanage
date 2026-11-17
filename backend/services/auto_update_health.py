# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""What the ``automatic_updates`` alert reads about one host (ROADMAP 26.5,
Enterprise).

The alerting engine decides what is a problem; this module only gathers the
facts, as plain values:

  last_run          the host's last automatic run that did something:
                    status, policy, reboot, whether someone acknowledged it
  rollout_halt      a halted rollout this host caused (26.4)
  policy            the policy the host follows and its hold
  hold_all          every policy held: since when and why
  critical_eligible each pending patch for a critical CVE the policy would
                    apply, and since when it may be (26.3) -- still there
                    long after that, it is overdue

Never raises: a host whose facts cannot be read has none.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.persistence import models
from backend.services import auto_update_runner as runner

logger = logging.getLogger(__name__)


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _last_run(db, host) -> Optional[Dict[str, Any]]:
    run = runner.last_run(db, host.id)
    if run is None:
        return None
    return {
        "status": run.status,
        "profile_name": run.profile_name,
        "queued_at": _iso(run.queued_at),
        "completed_at": _iso(run.completed_at),
        "acknowledged": run.acknowledged_at is not None,
        "reboot_status": run.reboot_status,
        "failed_count": run.failed_count,
    }


def _rollout_halt(db, host) -> Optional[Dict[str, Any]]:
    for rollout in db.query(models.AutoUpdateRollout).filter(
        models.AutoUpdateRollout.status == "halted"
    ):
        detail = rollout.halt_detail or {}
        if str(host.id) not in (detail.get("culprits") or []):
            continue
        stages = rollout.stages or []
        index = detail.get("stage", rollout.stage_index)
        fleet = stages[index] if 0 <= index < len(stages) else {}
        return {
            "profile_name": rollout.profile_name,
            "fleet": "" if fleet.get("remaining") else fleet.get("name", ""),
            "reason": rollout.halt_reason,
            "halted_at": _iso(rollout.halted_at),
        }
    return None


def _critical_eligible(db, eng, host, profile) -> List[Dict[str, Any]]:
    """The critical-CVE patches the policy would apply now, with the time
    each became eligible."""
    if not hasattr(eng, "update_eligibility"):
        return []
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_evidence,
    )

    settings = runner.settings_dict(runner.settings_row(db))
    updates = runner.update_dicts(db, host.id)
    auto_update_evidence.attach(db, host.id, updates)
    now = runner.now_naive()
    packages, _skipped = eng.classify_updates(updates, profile, settings, now)
    by_name = {(u["package_name"], u["package_manager"]): u for u in updates}
    out = []
    for package in packages:
        if package.get("kind") != "critical":
            continue
        update = by_name.get((package["package_name"], package["package_manager"]))
        if update is None:
            continue
        eligibility = eng.update_eligibility(update, profile, settings, now)
        out.append(
            {
                "package_name": package["package_name"],
                "fix_id": package.get("fix_id"),
                "eligible_at": _iso(eligibility.get("eligible_at")),
            }
        )
    return out


def _policy(db, eng, host) -> Optional[Dict[str, Any]]:
    tags = runner._tag_ids(db, [host.id]).get(  # pylint: disable=protected-access
        str(host.id), []
    )
    policies = runner.auto_profiles(db)
    winner = eng.resolve_policy({"id": str(host.id), "tag_ids": tags}, policies)
    if not winner:
        return None
    return next((p for p in policies if p["id"] == winner["profile_id"]), None)


def host_facts(db, host) -> Dict[str, Any]:
    """The facts about ``host`` the alert decides on (see the module doc)."""
    facts: Dict[str, Any] = {"last_run": None, "rollout_halt": None, "policy": None,
                             "hold_all": None, "critical_eligible": []}  # fmt: skip
    eng = runner.engine()
    if eng is None or not hasattr(eng, "plan_host_run"):
        return facts
    try:
        facts["last_run"] = _last_run(db, host)
        facts["rollout_halt"] = _rollout_halt(db, host)
        settings = runner.settings_row(db)
        if settings.hold_all:
            facts["hold_all"] = {"since": _iso(settings.hold_at),
                                 "reason": settings.hold_reason}  # fmt: skip
        if bool(getattr(host, "auto_update_opt_out", False)):
            return facts  # never patched automatically: nothing is overdue
        profile = _policy(db, eng, host)
        if profile is None:
            return facts
        row = db.get(models.UpgradeProfile, uuid.UUID(profile["id"]))
        facts["policy"] = {
            "name": profile["name"],
            "held": bool(row.held) if row else False,
            "hold_at": _iso(row.hold_at) if row else None,
            "hold_reason": row.hold_reason if row else None,
        }
        facts["critical_eligible"] = _critical_eligible(db, eng, host, profile)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Automatic updates: reading facts for host %s failed", host.id)
    return facts
