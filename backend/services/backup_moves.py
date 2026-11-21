# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Moving a host with its backups to another target (ROADMAP 27.3): copy,
then switch (Bryan, 2026-11-20).

A host's backups always live on one storage host, so a host that already
has backups does not simply start writing elsewhere:

1. **Copy.**  Its repository is copied into the new target the way an
   off-site copy is (``backup_replicas``): the source storage host copies
   each snapshot in through the new target's restate-proxy with a token of
   its own, and the new storage host keeps the copy under the move's id, in
   the very directory the host's own repository will have there.  The host
   goes on backing up to its old target meanwhile; a snapshot made since is
   copied too.
2. **Check.**  Once every snapshot is in, the new storage host protects the
   copy, checks it and lists it.  A failed check stops the move; the host
   stays where it is.
3. **Switch.**  When the listing holds every snapshot the host has, and
   nothing of the host's is running, its policy names the new target: the
   host, the new storage host (its own job files for the repository) and
   the old one (the host's grant leaves with the target's client list) are
   all told.  The old repository is kept as it is -- nothing backs up to it
   or prunes it -- until ``keep_until``: 14 days, or the old target's seal
   retention if that is longer.
4. **Retire.**  Then the old storage host removes it (``retire``; the
   agent removes only a repository it served itself for that policy).  The
   operator can remove it sooner (never before a seal of it would expire) or
   keep it for good.

Moving needs the new target to be reached through restate-proxy (a copy
goes into a repository only through a proxy or on the same machine) and the
source storage host's agent to copy (``replica_copy``).  Starting a move is
the license's (``backup_targets.chosen``); a move under way carries on
after a lapse, as off-site copying does.
"""

import logging
import posixpath
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_proxy as proxy
from backend.services import backup_replicas as replicas
from backend.websocket.messages import CommandType

logger = logging.getLogger(__name__)

COPYING, VERIFYING = replicas.MOVING
SWITCHED = "switched"
FAILED = "failed"
CANCELED = "canceled"
# The old repository is being removed, then is gone.
RETIRING = "retiring"
RETIRED = "retired"
# The old repository is still on the old target.
KEPT = (SWITCHED, RETIRING)
RETIRE = replicas.run_action("retire")
# The old repository is kept this long after the switch (Bryan, 2026-11-20).
GRACE_DAYS = 14
# A check that has not moved for this long is started again by the tick.
RETRY_HOURS = replicas.RETRY_HOURS

_REFUSALS = {
    "needs_proxy": lambda: _(
        "A host with backups can move only to a target reached through restate-proxy"
    ),
    "agent": lambda: _(
        "This host's storage host cannot copy backups yet; upgrade its agent"
    ),
    "previous": lambda: _(
        "This host still has backups from before its repository was "
        "encrypted; it can move once they have been pruned"
    ),
    "offsite": lambda: _(
        "That target holds this host's off-site copy; stop copying to it, or "
        "choose another target"
    ),
    "busy": lambda: _("This host is already moving to another target"),
    "kept": lambda: _(
        "This host's old repository is still kept on that target; remove it "
        "there first"
    ),
    "no_storage": lambda: _("That target has no storage host yet"),
}


def _target(db: Session, target_id: Any) -> Optional[models.BackupTarget]:
    return db.get(models.BackupTarget, target_id) if target_id else None


def _refuse(code: str) -> HTTPException:
    return HTTPException(status_code=409, detail=_REFUSALS[code]())


def has_history(db: Session, policy: Optional[models.BackupPolicy]) -> bool:
    """The host has snapshots it would lose by simply switching."""
    if policy is None:
        return False
    found = (
        db.query(models.BackupSnapshot.id)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
    )
    return found is not None


def under_way(db: Session, policy: models.BackupPolicy) -> Optional[models.BackupMove]:
    moves = replicas.moving(db, policy)
    return moves[0] if moves else None


def _previous_holds_snapshots(
    db: Session, policy: models.BackupPolicy, host: models.Host
) -> bool:
    if not policy.previous_repository_dir:
        return False
    for snapshot in (
        db.query(models.BackupSnapshot)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .all()
    ):
        if jobs.snapshot_repository(snapshot, policy, host) == jobs.PREVIOUS:
            return True
    return False


def _kept_on(
    db: Session, policy: models.BackupPolicy, target: models.BackupTarget
) -> bool:
    """The host's old repository from an earlier move is still on ``target``
    (moving back would copy into the very directory)."""
    found = (
        db.query(models.BackupMove.id)
        .filter(
            models.BackupMove.policy_id == policy.id,
            models.BackupMove.from_target_id == target.id,
            models.BackupMove.status.in_(KEPT),
        )
        .first()
    )
    return found is not None


def _refusal(
    db: Session,
    policy: models.BackupPolicy,
    host: models.Host,
    target: models.BackupTarget,
) -> Optional[str]:
    current = jobs.target_of(db, policy)
    if not target.storage_host_id:
        return "no_storage"
    if not proxy.uses_proxy(target):
        return "needs_proxy"
    if _kept_on(db, policy, target):
        return "kept"
    if replicas.ABILITY not in jobs.storage_abilities(policy):
        return "agent"
    if current is not None and str(current.replica_target_id or "") == str(target.id):
        return "offsite"
    if _previous_holds_snapshots(db, policy, host):
        return "previous"
    return None


def plan(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    db: Session,
    policy: Optional[models.BackupPolicy],
    host: models.Host,
    target: models.BackupTarget,
    actor: Optional[str],
) -> Optional[models.BackupMove]:
    """What saving ``host``'s policy with ``target`` means for its backups:
    the move it starts (or the one already going there) when the host has
    backups on another target -- its policy then stays where it is until
    the switch -- else None.  Saving it on the target it is on leaves a
    move under way alone (the dialog sends that target); only ``cancel``
    stops one."""
    if policy is None:
        return None
    going = under_way(db, policy)
    if policy.target_id == target.id:
        return going
    if going is not None:
        if going.target_id == target.id:
            return going
        raise _refuse("busy")
    if not has_history(db, policy):
        return None
    code = _refusal(db, policy, host, target)
    if code:
        raise _refuse(code)
    stamp = jobs.now()
    row = models.BackupMove(
        policy_id=policy.id,
        target_id=target.id,
        from_target_id=policy.target_id,
        repo_dir=jobs.policy_repo_dir(policy, host),
        status=COPYING,
        config_version=1,
        created_by=(actor or "")[:255] or None,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(row)
    db.flush()
    # The source storage host learns the copy, and makes its token for it.
    policy.config_version += 1
    proxy.sync_clients(db, target)
    return row


def cancel(db: Session, row: models.BackupMove) -> None:
    """Stop a move before its switch: the host stays where it is, and the
    copy so far stays on the new target's storage host as it is."""
    if row.status not in replicas.MOVING:
        return
    row.status = CANCELED
    row.updated_at = jobs.now()
    policy = db.get(models.BackupPolicy, row.policy_id)
    if policy is not None:
        policy.config_version += 1  # the source storage host drops the copy
    holder = db.get(models.BackupTarget, row.target_id)
    if holder is not None:
        proxy.sync_clients(db, holder)  # and its grant goes


def _fail(row: models.BackupMove, message: str) -> None:
    row.status = FAILED
    row.error = (message or "")[:1000] or None
    logger.error("Move %s of policy %s stopped: %s", row.id, row.policy_id, message)


# --- the steps after the copies -------------------------------------------


def _all_in(db: Session, row: models.BackupMove) -> bool:
    return not replicas.needed(db, row)


def _check(db: Session, row: models.BackupMove) -> None:
    """Every snapshot is in: protect, check, then list the copy."""
    row.status = VERIFYING
    replicas.queue_offsite(db, row, "protect")


def _busy(db: Session, policy: models.BackupPolicy) -> bool:
    """Anything of the host's still queued or running."""
    db.flush()
    found = (
        db.query(models.BackupRun.id)
        .filter(
            models.BackupRun.policy_id == policy.id,
            models.BackupRun.status.in_(jobs.PENDING),
        )
        .first()
    )
    return found is not None


def keep_days(old: Optional[models.BackupTarget]) -> int:
    """How long the old repository is kept: the grace period, or the old
    target's seal retention when that is longer (a seal is not cut short)."""
    sealing = old is not None and (old.seal_mode or "none") != "none"
    return max(GRACE_DAYS, (old.seal_keep_days or 0) if sealing else 0)


def try_switch(db: Session, row: models.BackupMove) -> bool:
    """Switch the policy to the new target once the copy holds everything
    and nothing of the host's is running; True when it switched."""
    policy = db.get(models.BackupPolicy, row.policy_id)
    if policy is None or row.status != VERIFYING or not row.verified_at:
        return False
    if not _all_in(db, row):
        row.status, row.verified_at = COPYING, None  # a newer snapshot came
        replicas.advance(db, row)
        return False
    if _busy(db, policy):
        return False  # the tick tries again
    old = db.get(models.BackupTarget, policy.target_id)
    stamp = jobs.now()
    policy.target_id = row.target_id
    policy.config_version += 1
    policy.updated_at = stamp
    row.status = SWITCHED
    row.switched_at = stamp
    row.keep_until = stamp + timedelta(days=keep_days(old))
    row.updated_at = stamp
    for target in (old, db.get(models.BackupTarget, row.target_id)):
        if target is not None:
            proxy.sync_clients(db, target)
    logger.info("Policy %s moved to target %s with its backups (move %s)",
                policy.id, row.target_id, row.id)  # fmt: skip
    return True


def _after_copy(db: Session, row, run, result) -> None:
    if not replicas.record_copy(row, run, result):
        return
    replicas.advance(db, row)
    if row.status == COPYING and _all_in(db, row):
        _check(db, row)


def _after_protect(db: Session, row, run, _result) -> None:
    if run.status != "ok":
        logger.warning("Move %s: protecting the copy ended %s", row.id, run.status)
    replicas.queue_offsite(db, row, "check")


def _after_check(db: Session, row, run, _result) -> None:
    if run.status != "ok":
        _fail(row, run.message or run.status)
        return
    replicas.queue_offsite(db, row, "du")


def _after_du(db: Session, row, run, result) -> bool:
    if run.status != "ok":
        _fail(row, run.message or run.status)
        return False
    replicas.record_du(row, run, result)
    row.verified_at = jobs.now()
    return try_switch(db, row)


def _after_prepare(db: Session, row, run, _result) -> None:
    if run.status == "ok":
        row.prepared_at = jobs.now()
        replicas.advance(db, row)
        if _all_in(db, row):
            _check(db, row)
    else:
        _fail(row, run.message or run.status)


_AFTER = {
    replicas.COPY: _after_copy,
    replicas.run_action("prepare"): _after_prepare,
    replicas.run_action("protect"): _after_protect,
    replicas.run_action("check"): _after_check,
    replicas.run_action("du"): _after_du,
}


def after(db: Session, run: models.BackupRun, result: Dict[str, Any]) -> bool:
    """What follows a copying run's result: a move's next step, or an
    off-site copy's (``backup_replicas.after``).  True when a move switched:
    the caller sends the new job files at once."""
    row = replicas.row_of(db, run)
    if not replicas.is_move(row):
        replicas.after(db, run, result)
        return False
    if run.action == RETIRE:
        if row.status == RETIRING:
            _after_retire(row, run)
        return False
    handler = _AFTER.get(run.action)
    if handler is None or row.status not in replicas.MOVING:
        return False
    switched = bool(handler(db, row, run, result))
    row.updated_at = jobs.now()
    return switched


def is_quiet_audit(db: Session, policy_id: Any, host_id: Any) -> bool:
    """A storage audit that is no policy's own but expected: an off-site
    copy's or a move's copy (under its row's id), or the old storage host's
    for a host moved away (it audits every repository it still holds)."""
    if replicas.is_offsite_audit(db, policy_id, host_id):
        return True
    for row in (
        db.query(models.BackupMove)
        .filter(
            models.BackupMove.policy_id == jobs.as_uuid(policy_id),
            models.BackupMove.status.in_(KEPT),
        )
        .all()
    ):
        old = _target(db, row.from_target_id)
        policy = db.get(models.BackupPolicy, row.policy_id)
        now_on = db.get(models.BackupTarget, policy.target_id) if policy else None
        if (
            old is not None
            and str(old.storage_host_id) == str(host_id)
            and (now_on is None or str(now_on.storage_host_id) != str(host_id))
        ):
            return True
    return False


# --- the scheduler ------------------------------------------------------


def tick(db: Session, now: datetime) -> None:
    """Switch a checked move that waited for the host to be idle, and start
    a check again that has not moved (copying itself is the replica tick's)."""
    for row in (
        db.query(models.BackupMove).filter(models.BackupMove.status == VERIFYING).all()
    ):
        if row.verified_at:
            try_switch(db, row)
            continue
        policy = db.get(models.BackupPolicy, row.policy_id)
        stale = (now - row.updated_at).total_seconds() >= RETRY_HOURS * 3600
        if stale and policy is not None and not _busy(db, policy):
            row.updated_at = now
            _check(db, row)
    for row in (
        db.query(models.BackupMove).filter(models.BackupMove.status == COPYING).all()
    ):
        if row.prepared_at and _all_in(db, row):
            _check(db, row)
    _retire_due(db, now)


# --- what the Backups page shows -----------------------------------------


def latest(db: Session, policy: models.BackupPolicy) -> Optional[models.BackupMove]:
    return (
        db.query(models.BackupMove)
        .filter(models.BackupMove.policy_id == policy.id)
        .order_by(models.BackupMove.created_at.desc())
        .first()
    )


def view(
    db: Session, policy: models.BackupPolicy, now: datetime
) -> Optional[Dict[str, Any]]:
    """The host's move under way, or the last one while its old repository
    is still kept; None otherwise."""
    row = latest(db, policy)
    if row is None or row.status in (CANCELED, RETIRED):
        return None
    target = db.get(models.BackupTarget, row.target_id)
    source = _target(db, row.from_target_id)
    total = (
        db.query(models.BackupSnapshot.id)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .count()
    )
    moving = row.status in replicas.MOVING
    return {
        "id": str(row.id),
        "status": row.status,
        "target": target.name if target else None,
        "from_target": source.name if source else None,
        "total": total,
        "behind": len(replicas.needed(db, row)) if moving else 0,
        "bytes": row.repository_bytes,
        "error": row.error or (row.last_copy_error if moving else None),
        "switched_at": row.switched_at.isoformat() if row.switched_at else None,
        "keep_until": row.keep_until.isoformat() if row.keep_until else None,
        # A sealed old repository is never removed before its seals expire.
        "removable_from": _iso(earliest_removal(db, row, now)),
    }


def move_or_404(db: Session, move_id: Any) -> models.BackupMove:
    row = db.get(models.BackupMove, jobs.as_uuid(move_id))
    if row is None:
        raise HTTPException(status_code=404, detail=_("Move not found"))
    return row


# --- retiring the old repository ------------------------------------------


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def old_repository(
    db: Session, row: models.BackupMove
) -> Optional[Tuple[models.BackupTarget, str]]:
    """The old target and the old repository's path on its storage host."""
    old = _target(db, row.from_target_id)
    if old is None or not old.storage_host_id or not old.storage_path:
        return None
    return old, posixpath.join(posixpath.normpath(old.storage_path), row.repo_dir)


def earliest_removal(
    db: Session, row: models.BackupMove, now: datetime
) -> Optional[datetime]:
    """When the old repository may first be removed, if later than ``now``:
    a sealing old target's seals of it run their course."""
    old = _target(db, row.from_target_id)
    if old is None or not row.switched_at or (old.seal_mode or "none") == "none":
        return None
    floor = row.switched_at + timedelta(days=old.seal_keep_days or 0)
    return floor if floor > now else None


def retire(db: Session, row: models.BackupMove) -> Optional[models.BackupRun]:
    """Ask the old storage host to remove the old repository (forgetting
    the policy there, unless the host moved within that storage host)."""
    policy = db.get(models.BackupPolicy, row.policy_id)
    found = old_repository(db, row)
    if policy is None or found is None or row.status != SWITCHED:
        return None
    old, path = found
    if str(policy.target_id) == str(old.id):
        return None  # it is on that target again: the repository is its own
    if jobs.pending(db, policy.id, RETIRE, old.storage_host_id):
        return None
    if _live_copy_on(db, policy, old):
        return None  # the agent forgets every entry naming that directory
    new = _target(db, policy.target_id)
    same = new is not None and str(new.storage_host_id) == str(old.storage_host_id)
    run = jobs.queue_command(
        db, policy, old.storage_host_id, RETIRE, CommandType.BACKUP_RUN,
        {"policy_id": str(policy.id), "action": "retire", "repository": path,
         "forget": not same},
        record={"replica_id": str(row.id)},
    )  # fmt: skip
    row.status, row.error, row.updated_at = RETIRING, None, jobs.now()
    logger.info("Move %s: removing the old repository %s", row.id, path)
    return run


def _live_copy_on(
    db: Session, policy: models.BackupPolicy, old: models.BackupTarget
) -> bool:
    """A copy of this host the old target still keeps under the same
    directory: its off-site copy, or a move into it under way."""
    replica = (
        db.query(models.BackupReplica.id)
        .filter(
            models.BackupReplica.policy_id == policy.id,
            models.BackupReplica.target_id == old.id,
        )
        .first()
    )
    moving = (
        db.query(models.BackupMove.id)
        .filter(
            models.BackupMove.policy_id == policy.id,
            models.BackupMove.target_id == old.id,
            models.BackupMove.status.in_(replicas.MOVING),
        )
        .first()
    )
    return replica is not None or moving is not None


def _after_retire(row: models.BackupMove, run: models.BackupRun) -> None:
    row.updated_at = jobs.now()
    if run.status == "ok":
        row.status, row.error = RETIRED, None
        logger.info("Move %s: the old repository is removed", row.id)
        return
    row.status = SWITCHED  # the tick tries again
    row.error = (run.message or run.status or "")[:1000] or None
    logger.error("Move %s: the old repository was not removed: %s", row.id, row.error)


def refused(db: Session, run: models.BackupRun, message: str) -> None:
    """A copying or retiring run the agent would not start."""
    replicas.refused(db, run, message)
    row = replicas.row_of(db, run)
    if run.action == RETIRE and replicas.is_move(row) and row.status == RETIRING:
        _after_retire(row, run)


def _retire_due(db: Session, now: datetime) -> None:
    """Remove each old repository whose keep date has passed (a failed
    removal is tried again after RETRY_HOURS); free a removal whose run was
    lost."""
    retry = timedelta(hours=RETRY_HOURS)
    for row in (
        db.query(models.BackupMove)
        .filter(
            models.BackupMove.status.in_(KEPT),
            models.BackupMove.keep_until.isnot(None),
            models.BackupMove.keep_until <= now,
        )
        .all()
    ):
        if row.status == RETIRING:
            policy_id = row.policy_id
            if now - row.updated_at >= retry and not jobs.pending(
                db, policy_id, RETIRE
            ):
                row.status = SWITCHED
            continue
        if row.error and now - row.updated_at < retry:
            continue
        if earliest_removal(db, row, now) is None:
            retire(db, row)


def remove_now(db: Session, row: models.BackupMove, now: datetime) -> None:
    """The operator's "Remove now": 409 unless the move switched and no
    seal of the old repository is still running its course."""
    if row.status != SWITCHED:
        raise HTTPException(
            status_code=409, detail=_("This move's old repository is no longer kept")
        )
    floor = earliest_removal(db, row, now)
    if floor is not None:
        raise HTTPException(
            status_code=409,
            detail=_(
                "The old target seals its backups; this old repository can be "
                "removed from %s"
            )
            % floor.strftime("%Y-%m-%d"),
        )
    row.keep_until, row.error = now, None
    retire(db, row)


def keep(row: models.BackupMove) -> None:
    """The operator's "Keep": the old repository stays until removed."""
    if row.status != SWITCHED:
        raise HTTPException(
            status_code=409, detail=_("This move's old repository is no longer kept")
        )
    row.keep_until, row.error, row.updated_at = None, None, jobs.now()
