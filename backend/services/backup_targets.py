# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Multiple backup targets (ROADMAP 27.3, Enterprise ``backup_ops_engine``).

Community has one target.  With the engine, an installation has several,
one of them the default: a new host policy uses the default unless it (or
the tag policy that gives it) names another.  After a license lapse every
target keeps backing up and restoring -- a lapse never holds anyone's
backups hostage -- but nothing is added and no host moves between targets
until it is licensed again (Bryan, 2026-11-20).

The engine decides whether a target may stand beside the others
(``target_refusal``); this module gathers the facts and owns the 402.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
from backend.licensing.migration_compat import missing_engine_detail
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs

ENGINE = "backup_ops_engine"

_REFUSALS = {
    "same_name": (409, lambda: _("Another backup target has that name")),
    "same_storage": (
        409,
        lambda: _(
            "Another backup target already uses that storage path on that "
            "storage host, or one inside it or around it"
        ),
    ),
    "same_mount_point": (
        409,
        lambda: _("Another backup target already uses that host mount point"),
    ),
}


def engine():
    """The loaded engine with target support, or None (unlicensed, or an
    older build): then only the default target takes new hosts."""
    eng = module_loader.get_module(ENGINE)
    return eng if hasattr(eng, "target_refusal") else None


def engine_or_402():
    eng = engine()
    if eng is None:
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                ENGINE,
                _("More than one backup target needs the Enterprise backup "
                  "operations engine"),
            ),
        )  # fmt: skip
    return eng


def facts(target: Any) -> Dict[str, Any]:
    """What the engine compares: a target row or a request body."""
    storage = getattr(target, "storage_host_id", None)
    return {
        "id": str(getattr(target, "id", "") or ""),
        "name": getattr(target, "name", None),
        "storage_host_id": str(storage) if storage else None,
        "storage_path": getattr(target, "storage_path", None),
        "host_mount_point": getattr(target, "host_mount_point", None),
    }


def refuse_clash(db: Session, candidate: Any, own_id: Any = None) -> None:
    """Refuse a target that would collide with another one (the engine
    decides); nothing to compare against with one target, or unlicensed."""
    others = [t for t in jobs.targets(db) if str(t.id) != str(own_id or "")]
    eng = engine()
    if not others or eng is None:
        return
    code = eng.target_refusal(facts(candidate), [facts(t) for t in others])
    if code:
        status, text = _REFUSALS[code]
        raise HTTPException(status_code=status, detail=text())


_REPLICA_REFUSALS = {
    "self": lambda: _("A backup target cannot be its own off-site copy"),
    "not_proxy": lambda: _(
        "The off-site copy must be a target reached through restate-proxy, "
        "so this site can add to it but never delete from it"
    ),
    "same_storage_host": lambda: _(
        "The off-site copy must be on another storage host; one on the same "
        "storage host is lost with it"
    ),
    "cycle": lambda: _(
        "That target already copies, directly or through others, to this one"
    ),
}


def _replica_facts(target: models.BackupTarget) -> Dict[str, Any]:
    return dict(
        facts(target),
        transport=getattr(target, "transport", None),
        proxy_host=getattr(target, "proxy_host", None),
    )


def set_replica(
    db: Session, target: models.BackupTarget, replica_id: Optional[str]
) -> Optional[models.BackupTarget]:
    """Name (or clear) the target ``target`` copies off-site to.  Enterprise
    either way: after a lapse copies go on as they are, frozen."""
    eng = engine_or_402()
    if not replica_id:
        target.replica_target_id = None
        return None
    replica = target_or_404(db, replica_id)
    replica_of = {
        str(t.id): str(t.replica_target_id)
        for t in jobs.targets(db)
        if getattr(t, "replica_target_id", None) and str(t.id) != str(target.id)
    }
    if not hasattr(eng, "replica_refusal"):
        raise HTTPException(
            status_code=402,
            detail=missing_engine_detail(
                ENGINE, _("Off-site copies need a newer backup operations engine")
            ),
        )
    code = eng.replica_refusal(
        _replica_facts(target), _replica_facts(replica), replica_of
    )
    if code:
        raise HTTPException(status_code=409, detail=_REPLICA_REFUSALS[code]())
    target.replica_target_id = replica.id
    return replica


def copies_into(db: Session, target: models.BackupTarget) -> List[models.BackupTarget]:
    """The targets that copy off-site into ``target``."""
    return [
        t for t in jobs.targets(db)
        if str(getattr(t, "replica_target_id", None) or "") == str(target.id)
    ]  # fmt: skip


def target_or_404(db: Session, target_id: Any) -> models.BackupTarget:
    try:
        key = uuid.UUID(str(target_id))
    except ValueError as bad:
        raise HTTPException(
            status_code=404, detail=_("Backup target not found")
        ) from bad
    target = db.get(models.BackupTarget, key)
    if target is None:
        raise HTTPException(status_code=404, detail=_("Backup target not found"))
    return target


def chosen(
    db: Session,
    target_id: Optional[str],
    current: Optional[models.BackupTarget] = None,
) -> models.BackupTarget:
    """The target a policy is to use: ``target_id`` when given, else the
    one it already has (``current``), else the default.  Keeping a policy
    where it is, or putting a new one on the default, needs no license;
    anything else does (402) -- so a lapse freezes, never breaks."""
    if target_id:
        target = target_or_404(db, target_id)
    else:
        target = current or jobs.default_target(db)
    if target is None:
        raise HTTPException(status_code=409, detail=_("Set up the backup target first"))
    if current is not None and target.id == current.id:
        return target
    default = jobs.default_target(db)
    if current is None and default is not None and target.id == default.id:
        return target
    engine_or_402()
    return target


def refuse_move_with_history(db: Session, policy, target) -> None:
    """A host with backups stays on its target for now: moving it copies its
    repository to the new target first, then switches (27.3 step 4)."""
    if policy is None or policy.target_id == target.id:
        return
    has_history = (
        db.query(models.BackupSnapshot.id)
        .filter(
            models.BackupSnapshot.policy_id == policy.id,
            models.BackupSnapshot.gone_at.is_(None),
        )
        .first()
        is not None
    )
    if has_history:
        raise HTTPException(
            status_code=409,
            detail=_(
                "This host already has backups on its target; it cannot move "
                "to another target yet"
            ),
        )


def in_use(db: Session, target) -> Dict[str, int]:
    """How many host policies and tag policies name ``target``."""
    return {
        "hosts": db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.target_id == target.id)
        .count(),
        "tag_policies": db.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.target_id == target.id)
        .count(),
    }


def make_default(db: Session, target) -> None:
    for other in jobs.targets(db):
        other.is_default = other.id == target.id


def brief(db: Session) -> List[Dict[str, Any]]:
    """Every target in a line each, the default first: for pickers."""
    default = jobs.default_target(db)
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "location": t.location,
            "is_default": default is not None and t.id == default.id,
            **in_use(db, t),
        }
        for t in jobs.targets(db)
    ]
