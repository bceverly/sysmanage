# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet restore jobs (ROADMAP 27.2, Enterprise ``backup_ops_engine``).

One restore asked of many hosts -- the same paths on each, from each host's
own newest snapshot or its newest taken before a moment (the last good one
before an incident) -- released in waves so that no more than the job's
concurrency run at once.  Each host's restore goes through exactly the path
a single restore takes (``backups_restore_flow.perform``): the same checks,
the same audit entry, the same run; a host that cannot take it (not
equipped, its storage unreachable, no snapshot old enough) is recorded with
why and the others go on.

The backup tick advances running jobs (``tick``); creating or approving a
job starts its first wave at once.  A restore in place (for real) is held
for a second approver as one four-eyes request of kind ``fleet_restore``
when the tenant has four-eyes on.  The engine decides the wave size and
which snapshot each host restores; without it nothing is created or
advanced.
"""

import json
import logging
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_four_eyes as four_eyes
from backend.services import backup_jobs as jobs

logger = logging.getLogger(__name__)

ENGINE = "backup_ops_engine"
KIND = "fleet_restore"

AWAITING = "awaiting_approval"
RUNNING = "running"
COMPLETED = "completed"
CANCELED = "canceled"
REJECTED = "rejected"

WAITING = "waiting"
STARTED = "running"
OK = "ok"
FAILED = "failed"
SKIPPED = "skipped"


def engine():
    """The loaded engine, or None -- also for one without fleet restores."""
    eng = module_loader.get_module(ENGINE)
    return eng if hasattr(eng, "fleet_release") else None


def _iso(when: Optional[datetime]) -> Optional[str]:
    return when.isoformat() if when is not None else None


def _actor(job: models.BackupFleetRestore):
    """Each host's restore is done as the person who asked for the job."""
    return SimpleNamespace(id=None, userid=job.created_by)


def create(  # pylint: disable=too-many-arguments
    db: Session,
    user,
    eng,
    *,
    name: str,
    hosts: Iterable[models.Host],
    include: List[str],
    exclude: List[str],
    before: Optional[datetime],
    in_place: bool,
    dry_run: bool,
    allow_unsigned: bool,
    concurrency: Optional[int],
) -> models.BackupFleetRestore:
    """A new job with one waiting target per host; held for a second
    approver when four-eyes asks for it, else started."""
    job = models.BackupFleetRestore(
        name=name,
        include=json.dumps(include),
        exclude=json.dumps(exclude),
        before_at=before,
        in_place=in_place,
        dry_run=dry_run,
        allow_unsigned=allow_unsigned,
        concurrency=eng.fleet_concurrency(concurrency),
        status=RUNNING,
        created_by=user.userid,
        created_at=jobs.now(),
    )
    for position, host in enumerate(hosts):
        job.targets.append(
            models.BackupFleetRestoreTarget(
                host_id=host.id, status=WAITING, position=position
            )
        )
    db.add(job)
    db.flush()
    first = db.get(models.Host, job.targets[0].host_id)
    held = four_eyes.hold_request(
        db,
        user,
        first,
        kind=KIND,
        # The paths too: the second person approves overwriting THESE files
        # on every host, and the card showed only the job's name (2026-11-25).
        payload={
            "job_id": str(job.id),
            "name": name,
            "hosts": len(job.targets),
            "include": list(include),
        },
        facts={"in_place": in_place, "dry_run": dry_run},
        audit_text="Fleet restore requested; waits for a second approver",
        target={"fleet_restore_id": str(job.id)},
    )
    if held is not None:
        job.status = AWAITING
        db.commit()
        return job
    db.commit()
    advance(db, eng, job)
    return job


def approve(db: Session, eng, job: models.BackupFleetRestore, approver: str) -> None:
    """A second person approved it: start the first wave."""
    job.status, job.approved_by = RUNNING, approver
    db.commit()
    advance(db, eng, job)


def cancel(db: Session, job: models.BackupFleetRestore) -> int:
    """Stop releasing hosts; restores already running finish.  How many
    waiting hosts were canceled."""
    canceled = 0
    for target in job.targets:
        if target.status == WAITING:
            target.status, target.finished_at = CANCELED, jobs.now()
            canceled += 1
    if job.status in (RUNNING, AWAITING):
        job.status = CANCELED
        if not any(t.status == STARTED for t in job.targets):
            job.finished_at = jobs.now()
    db.commit()
    return canceled


def _sync(db: Session, job: models.BackupFleetRestore, now: datetime) -> None:
    """Running targets whose restore has finished."""
    for target in job.targets:
        if target.status != STARTED or target.run_id is None:
            continue
        run = db.get(models.BackupRun, target.run_id)
        if run is None:
            target.status, target.message = FAILED, "The restore's run is gone"
        elif run.status in jobs.FINAL:
            target.status = OK if run.status == "ok" else FAILED
            if target.status == FAILED:
                target.message = (run.message or run.status)[:500]
        else:
            continue
        target.finished_at = now


def _refused(target, now: datetime, status: str, message: str) -> None:
    target.status, target.message, target.finished_at = status, message[:500], now


def _start(db: Session, eng, job, target, now: datetime) -> None:
    """Send one host its restore, through the single-restore path."""
    # pylint: disable=import-outside-toplevel
    from backend.api import backups_restore_flow as restore_flow
    from backend.api.backups import RestoreBody, _ready_policy
    from backend.services import backup_reach as reach

    host = db.get(models.Host, target.host_id)
    if host is None:
        _refused(target, now, SKIPPED, "The host no longer exists")
        return
    try:
        policy = _ready_policy(db, host)
        reach.refuse_if_blocked(db, host)
    except HTTPException as exc:
        _refused(target, now, SKIPPED, str(exc.detail))
        return
    snaps = (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .all()
    )
    name = eng.pick_snapshot(
        [{"name": s.name, "created_at": s.created_at} for s in snaps], job.before_at
    )
    if name is None:
        _refused(target, now, SKIPPED, "No snapshot to restore from")
        return
    body = RestoreBody(
        snapshot=name,
        include=json.loads(job.include),
        exclude=json.loads(job.exclude or "[]"),
        dry_run=job.dry_run,
        acknowledge_unsigned=job.allow_unsigned,
        in_place=job.in_place,
        acknowledge_in_place=job.in_place,
    )
    try:
        out = restore_flow.perform(
            db, _actor(job), host, policy, body, approved_by=job.approved_by
        )
    except HTTPException as exc:
        # perform refuses before it queues anything: nothing to undo.
        _refused(target, now, FAILED, str(exc.detail))
        return
    target.snapshot, target.status, target.started_at = name, STARTED, now
    target.run_id = uuid.UUID(out["id"])


def advance(db: Session, eng, job: models.BackupFleetRestore, now=None) -> None:
    """Record finished hosts, release the next wave, close the job when
    every host is done."""
    now = now or jobs.now()
    _sync(db, job, now)
    if job.status == RUNNING:
        # A host refused as it is released (no policy, no snapshot, not
        # signed) takes no slot: the next one is tried in its place, so a
        # wave is ``concurrency`` hosts actually restoring.  It used to cost
        # its slot until the next tick -- with concurrency 1, three refused
        # hosts took three ticks (lab, 2026-11-25).
        waiting = [t for t in job.targets if t.status == WAITING]
        in_flight = sum(1 for t in job.targets if t.status == STARTED)
        room = eng.fleet_release(job.concurrency, in_flight, len(waiting))
        for target in waiting:
            if room <= 0:
                break
            db.commit()  # what is recorded so far survives a failure below
            _start(db, eng, job, target, now)
            if target.status == STARTED:
                room -= 1
    if job.status in (RUNNING, CANCELED) and not any(
        t.status in (WAITING, STARTED) for t in job.targets
    ):
        if job.status == RUNNING:
            job.status = COMPLETED
        job.finished_at = job.finished_at or now
    db.commit()


def _settle_held(db: Session, eng, now: datetime) -> None:
    """A held job whose request was rejected, withdrawn or expired is over."""
    held = db.query(models.BackupFleetRestore).filter(
        models.BackupFleetRestore.status == AWAITING
    )
    for job in held:
        request = (
            db.query(models.BackupRestoreRequest)
            .filter(
                models.BackupRestoreRequest.kind == KIND,
                models.BackupRestoreRequest.target.like('%"' + str(job.id) + '"%'),
            )
            .first()
        )
        if request is None:
            continue
        state = eng.request_state(
            {"status": request.status, "requested_at": request.requested_at}, now
        )
        if state in ("rejected", "withdrawn", "expired"):
            # Withdrawn is the requester calling it off -- a cancel, not a
            # rejection (it read "rejected", lab 2026-11-25).
            job.status = CANCELED if state == "withdrawn" else REJECTED
            job.finished_at = now
            for target in job.targets:
                target.status = CANCELED
    db.commit()


def tick(db: Session, now: Optional[datetime] = None) -> None:
    """The backup tick's pass over this database's fleet restores."""
    eng = engine()
    if eng is None:
        return
    now = now or jobs.now()
    _settle_held(db, eng, now)
    live = db.query(models.BackupFleetRestore).filter(
        models.BackupFleetRestore.status.in_((RUNNING, CANCELED)),
        models.BackupFleetRestore.finished_at.is_(None),
    )
    for job in live.all():
        try:
            advance(db, eng, job, now)
        except Exception:  # pylint: disable=broad-except
            db.rollback()
            logger.exception("Fleet restore %s could not advance", job.id)


def view(
    db: Session, job: models.BackupFleetRestore, hosts: bool = False
) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for target in job.targets:
        counts[target.status] = counts.get(target.status, 0) + 1
    out: Dict[str, Any] = {
        "id": str(job.id),
        "name": job.name,
        "status": job.status,
        "include": json.loads(job.include),
        "exclude": json.loads(job.exclude or "[]"),
        "before": _iso(job.before_at),
        "in_place": job.in_place,
        "dry_run": job.dry_run,
        "concurrency": job.concurrency,
        "created_by": job.created_by,
        "created_at": _iso(job.created_at),
        "approved_by": job.approved_by,
        "finished_at": _iso(job.finished_at),
        "hosts": len(job.targets),
        "counts": counts,
    }
    if hosts:
        out["targets"] = []
        for target in job.targets:
            host = db.get(models.Host, target.host_id)
            out["targets"].append({
                "host_id": str(target.host_id),
                "fqdn": host.fqdn if host else None,
                "status": target.status,
                "snapshot": target.snapshot,
                "run_id": str(target.run_id) if target.run_id else None,
                "message": target.message,
                "started_at": _iso(target.started_at),
                "finished_at": _iso(target.finished_at),
            })  # fmt: skip
    return out
