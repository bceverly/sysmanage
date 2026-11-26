# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-by-fleet rollout of automatic updates (ROADMAP 26.4, Enterprise).

A policy with ``rollout_enabled`` does not patch every host it covers when
it fires: it starts a rollout.  Its fleets (``UpgradeProfileRolloutStage``:
a name, a tag, a soak time) go one at a time, the first being the canary;
each host is patched with the first fleet whose tag it carries, once, and
hosts in no fleet go last.  The plan is fixed when the rollout starts.

Each tick, a running rollout asks the engine's ``rollout_gate`` about its
current fleet: still in flight (each host applies only inside its own
windows and only eligible updates, 26.2 / 26.3), soaking, healthy (the next
fleet starts), or unhealthy -- the rollout halts, says why and names the
hosts, and nothing more is patched until a person resumes or cancels it.
While a rollout is running or halted the policy does not start another.

The decisions are the Enterprise ``automation_engine``'s; this module reads
and writes the database.  An engine older than 26.4 has no
``rollout_gate``: policies then apply per host, as before.
"""

import copy
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm.attributes import flag_modified

from backend.i18n import _
from backend.persistence import models
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)

RUNNING = "running"
HALTED = "halted"
COMPLETED = "completed"
CANCELED = "canceled"
OPEN = (RUNNING, HALTED)
POLICY_GONE = "policy_deleted"
ACTOR = "automatic updates"


def aligned(eng) -> bool:
    """Does this engine know rollouts (26.4)?"""
    return eng is not None and hasattr(eng, "rollout_gate")


def enabled(eng, profile_row) -> bool:
    return bool(getattr(profile_row, "rollout_enabled", False)) and aligned(eng)


def stage_rows(db, profile_id) -> List[models.UpgradeProfileRolloutStage]:
    return (
        db.query(models.UpgradeProfileRolloutStage)
        .filter(models.UpgradeProfileRolloutStage.profile_id == profile_id)
        .order_by(models.UpgradeProfileRolloutStage.position)
        .all()
    )


def open_rollout(db, profile_id) -> Optional[models.AutoUpdateRollout]:
    """The policy's running or halted rollout, if any."""
    return (
        db.query(models.AutoUpdateRollout)
        .filter(
            models.AutoUpdateRollout.profile_id == profile_id,
            models.AutoUpdateRollout.status.in_(OPEN),
        )
        .first()
    )


def _iso(value):
    return value.isoformat() if value else None


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except ValueError:
        return None


def _save(rollout, stages, now) -> None:
    rollout.stages = stages
    rollout.updated_at = now
    flag_modified(rollout, "stages")


def _audit(db, rollout, description, username=None, details=None) -> None:
    AuditService.log(
        db=db,
        action_type=ActionType.EXECUTE,
        entity_type=EntityType.UPDATE_POLICY,
        entity_id=str(rollout.id),
        entity_name=rollout.profile_name,
        description=description,
        result=Result.SUCCESS,
        username=username or ACTOR,
        details=details,
        commit=False,
    )


# ---------------------------------------------------------------------------
# starting a rollout, firing a fleet
# ---------------------------------------------------------------------------


def start(db, eng, profile_row, hosts, tags, now, triggered_by, summary):
    """The policy fired: start its rollout with the first fleet -- or, when
    one is still running or halted, start nothing."""
    if open_rollout(db, profile_row.id) is not None:
        summary["rollout_active"] = summary.get("rollout_active", 0) + 1
        return None
    stages = eng.rollout_assign(
        [{"id": str(h.id), "tag_ids": tags.get(str(h.id), [])} for h in hosts],
        [
            {"name": s.name, "tag_id": str(s.tag_id) if s.tag_id else None,
             "soak_minutes": s.soak_minutes or 0}  # fmt: skip
            for s in stage_rows(db, profile_row.id)
        ],
    )
    for stage in stages:
        stage.update(status="pending", started_at=None, finished_at=None)
    rollout = models.AutoUpdateRollout(
        id=uuid.uuid4(),
        profile_id=profile_row.id,
        profile_name=profile_row.name,
        status=RUNNING,
        stage_index=0,
        stages=stages,
        triggered_by=triggered_by,
        started_at=now,
        updated_at=now,
    )
    db.add(rollout)
    db.flush()
    _audit(
        db,
        rollout,
        _("Rollout of policy '%(policy)s' started: %(count)d fleet(s)")
        % {"policy": profile_row.name, "count": len(stages)},
        username=triggered_by,
        details={"stages": [{"name": s["name"], "hosts": len(s["host_ids"])}
                            for s in stages]},  # fmt: skip
    )
    summary["rollouts_started"] = summary.get("rollouts_started", 0) + 1
    advance(db, eng, rollout, profile_row, now, summary)
    return rollout


def _fire_stage(db, eng, rollout, index, profile_row, now, summary) -> None:
    """Plan and send (or record why not) every host of fleet ``index``."""
    from backend.services import (  # pylint: disable=import-outside-toplevel
        auto_update_runner as runner,
    )

    stages = copy.deepcopy(rollout.stages)
    stage = stages[index]
    ids = [uuid.UUID(h) for h in stage["host_ids"]]
    hosts = db.query(models.Host).filter(models.Host.id.in_(ids)).all() if ids else []
    # A host deleted since the rollout started has nothing left to patch.
    stage["host_ids"] = [str(h.id) for h in hosts]
    stage.update(status=RUNNING, started_at=_iso(now))
    rollout.stage_index = index
    _save(rollout, stages, now)
    db.flush()
    settings = runner.settings_dict(runner.settings_row(db))
    host_ids = runner.profile_host_ids(db, [profile_row.id]).get(str(profile_row.id))
    profile = runner.profile_dict(profile_row, host_ids)
    tags = runner._tag_ids(
        db, [h.id for h in hosts]
    )  # pylint: disable=protected-access
    runner.fire_hosts(
        db, eng, profile, hosts, tags, settings, now, rollout.triggered_by,
        summary, rollout=(rollout.id, index),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# the gate between fleets
# ---------------------------------------------------------------------------


def _latest_runs(db, rollout_id, index) -> List[Dict[str, Any]]:
    runs = (
        db.query(models.AutoUpdateRun)
        .filter(
            models.AutoUpdateRun.rollout_id == rollout_id,
            models.AutoUpdateRun.rollout_stage == index,
        )
        .order_by(models.AutoUpdateRun.queued_at)
        .all()
    )
    latest: Dict[str, models.AutoUpdateRun] = {}
    for run in runs:
        latest[str(run.host_id)] = run
    return [
        {
            "host_id": host_id,
            "status": run.status,
            "reboot_status": run.reboot_status,
            # It applied a fix for a critical CVE: the gate skips the soak.
            "critical": any(
                isinstance(p, dict) and p.get("kind") == "critical"
                for p in run.packages or []
            ),
        }
        for host_id, run in latest.items()
    ]


def _not_reporting(db, runs) -> List[str]:
    applied = [uuid.UUID(r["host_id"]) for r in runs
               if r["status"] in ("succeeded", "partial")]  # fmt: skip
    if not applied:
        return []
    return [
        str(h.id)
        for h in db.query(models.Host).filter(models.Host.id.in_(applied))
        if (h.status or "up") != "up"
    ]


def _critical_alerts(db, host_ids, since) -> List[Dict[str, Any]]:
    if not host_ids or since is None:
        return []
    rows = (
        db.query(models.Alert.host_id, models.Alert.title)
        .filter(
            models.Alert.host_id.in_([uuid.UUID(h) for h in host_ids]),
            models.Alert.severity == "critical",
            models.Alert.triggered_at >= since,
        )
        .all()
    )
    return [{"host_id": str(host_id), "title": title} for host_id, title in rows]


def stage_facts(db, rollout, index, profile_row) -> Dict[str, Any]:
    """What the engine's gate needs to know about fleet ``index`` now."""
    stage = rollout.stages[index]
    runs = _latest_runs(db, rollout.id, index)
    return {
        "host_ids": stage["host_ids"],
        "runs": runs,
        "finished_at": _parse(stage.get("finished_at")),
        "soak_minutes": stage.get("soak_minutes") or 0,
        "max_failure_pct": getattr(profile_row, "rollout_max_failure_pct", 0) or 0,
        "not_reporting": _not_reporting(db, runs),
        "critical_alerts": _critical_alerts(
            db, stage["host_ids"], _parse(stage.get("started_at"))
        ),
        "forced": bool(stage.get("forced")),
    }


def _halt(db, rollout, index, gate, now) -> None:
    stages = copy.deepcopy(rollout.stages)
    stages[index].update(status=HALTED, counts=gate["counts"])
    rollout.status, rollout.halted_at = HALTED, now
    rollout.halt_reason = gate["reason"]
    rollout.halt_detail = {
        "stage": index,
        "culprits": gate["culprits"],
        **{
            k: gate[k]
            for k in ("failure_pct", "max_failure_pct", "alerts")
            if k in gate
        },
    }
    _save(rollout, stages, now)
    _audit(
        db,
        rollout,
        _("Rollout of policy '%(policy)s' halted at fleet '%(fleet)s': %(reason)s")
        % {"policy": rollout.profile_name, "fleet": stages[index]["name"],
           "reason": gate["reason"]},  # fmt: skip
        details=rollout.halt_detail,
    )


def _finish_stage(rollout, index, gate, now) -> None:
    stages = copy.deepcopy(rollout.stages)
    stage = stages[index]
    stage.update(status="done", counts=gate["counts"])
    stage["finished_at"] = stage.get("finished_at") or _iso(now)
    _save(rollout, stages, now)


def _keep_waiting(rollout, index, gate, now) -> None:
    """The fleet is still running, or soaking: record where it stands."""
    stages = copy.deepcopy(rollout.stages)
    stages[index]["counts"] = gate["counts"]
    if gate["action"] == "soak" and not stages[index].get("finished_at"):
        stages[index]["finished_at"] = _iso(now)
    stages[index]["soak_until"] = _iso(gate.get("until"))
    _save(rollout, stages, now)


def _complete(db, rollout, now) -> None:
    rollout.status, rollout.completed_at = COMPLETED, now
    _audit(
        db,
        rollout,
        _("Rollout of policy '%(policy)s' completed")
        % {"policy": rollout.profile_name},
    )


def advance(db, eng, rollout, profile_row, now, summary=None) -> None:
    """Move ``rollout`` on as far as its fleets' health allows right now."""
    summary = summary if summary is not None else {}
    for _step in range(len(rollout.stages) + 1):
        index = rollout.stage_index
        stage = rollout.stages[index]
        if stage.get("status") == "pending":
            _fire_stage(db, eng, rollout, index, profile_row, now, summary)
            stage = rollout.stages[index]
        if not stage["host_ids"]:
            gate = {"action": "advance", "counts": {"hosts": 0}}
        else:
            gate = eng.rollout_gate(stage_facts(db, rollout, index, profile_row), now)
        if gate["action"] == "halt":
            _halt(db, rollout, index, gate, now)
            summary["halted"] = summary.get("halted", 0) + 1
            return
        if gate["action"] in ("wait", "soak"):
            _keep_waiting(rollout, index, gate, now)
            return
        _finish_stage(rollout, index, gate, now)
        if gate.get("reason") == "critical_fix":
            _audit(
                db,
                rollout,
                _(
                    "Rollout of policy '%(policy)s' moved on from fleet "
                    "'%(fleet)s' without the waiting time: the fleet applied "
                    "a critical fix and stayed healthy"
                )
                % {"policy": rollout.profile_name, "fleet": stage["name"]},
            )
        if index + 1 >= len(rollout.stages):
            _complete(db, rollout, now)
            return
        rollout.stage_index = index + 1


def advance_rollouts(db, eng, now) -> Dict[str, int]:
    """One pass over every running rollout (the tick)."""
    summary: Dict[str, int] = {}
    if not aligned(eng):
        return summary
    for rollout in (
        db.query(models.AutoUpdateRollout)
        .filter(models.AutoUpdateRollout.status == RUNNING)
        .all()
    ):
        profile_row = (
            db.get(models.UpgradeProfile, rollout.profile_id)
            if rollout.profile_id
            else None
        )
        if profile_row is None:
            end(db, rollout, CANCELED, now, None, POLICY_GONE)
            continue
        if profile_row.held:
            continue  # a hold pauses the rollout between fleets too
        try:
            advance(db, eng, rollout, profile_row, now, summary)
            db.commit()
        except Exception:  # pylint: disable=broad-exception-caught
            db.rollback()
            logger.exception(
                "Automatic updates: rollout %s failed to advance", rollout.id
            )
    return summary


# ---------------------------------------------------------------------------
# a person resumes or cancels
# ---------------------------------------------------------------------------


def resume(db, rollout, username, reason, now) -> None:
    """Continue a halted rollout: its current fleet counts as done and the
    next one starts on the next tick."""
    stages = copy.deepcopy(rollout.stages)
    stages[rollout.stage_index].update(forced=True, resumed_by=username,
                                       resume_reason=reason)  # fmt: skip
    rollout.status = RUNNING
    rollout.ended_by, rollout.end_reason = username, reason
    _save(rollout, stages, now)
    _audit(
        db,
        rollout,
        _("Rollout of policy '%(policy)s' resumed past fleet '%(fleet)s'")
        % {"policy": rollout.profile_name,
           "fleet": stages[rollout.stage_index]["name"]},  # fmt: skip
        username=username,
        details={"reason": reason, "halt_reason": rollout.halt_reason},
    )


def end(db, rollout, status, now, username, reason) -> None:
    """Cancel (or close) a rollout: no further fleet is patched.  Runs
    already queued in the current fleet still go out."""
    rollout.status, rollout.completed_at = status, now
    rollout.ended_by, rollout.end_reason = username, reason
    rollout.updated_at = now
    _audit(
        db,
        rollout,
        _("Rollout of policy '%(policy)s' canceled") % {"policy": rollout.profile_name},
        username=username,
        details={"reason": reason},
    )
