# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Backup policies by tag (Pro+ backup_engine, ROADMAP 24.6, 2026-11-03).

A tag policy is a template, not a second scheduling path: every host that
carries its tag gets its settings on the host's own ``backup_policy`` row --
the row the scheduler, the storage side and the results already run -- with
``tag_policy_id`` naming where they came from.  Bryan's rule (2026-11-02):

* where several tag policies cover a host, the lowest ``priority`` wins
  (then the older one, then the name, so the choice never flips between
  passes);
* a host's own policy -- one saved with Configure (``tag_policy_id`` NULL) --
  always beats every tag policy;
* a host no tag policy covers any more keeps its policy as its own, paused
  (scheduling stops; Configure turns it back on).  It is never deleted: the
  row carries the repository's encryption keys, their rotation history, the
  run history and the snapshot list, and deleting it cascades all of them --
  lab, 2026-11-03: removing a proof's tag policy deleted t14's policy, and an
  encrypted, signed host was left with a blank, unencrypted one.

``resolve`` is idempotent: a policy whose settings already match is left
alone, so its job files are not re-sent.  It runs when a tag policy is
saved or removed and on every scheduler pass (tags change elsewhere), and
only while the backup engine is loaded -- without it nothing new is applied
and what was applied keeps running.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.services import backup_jobs as jobs
from backend.services import backup_reach as reach
from backend.services.audit_service import ActionType, AuditService, EntityType

logger = logging.getLogger(__name__)

# The per-host policy fields a tag policy sets (backups.PolicyBody).
SCALARS = (
    "enabled",
    "interval_hours",
    "window_start_hour",
    "keep_last",
    "check_interval_days",
    "quiesce",
)
# Optional counts: 0 / missing is stored as NULL ("not used").
COUNTS = (
    "keep_daily",
    "keep_weekly",
    "keep_monthly",
    "keep_yearly",
    "verify_interval_days",
)
LISTS = ("quiesce_with", "keep_paths", "skip_paths")


def engine_loaded() -> bool:
    return module_loader.get_module("backup_engine") is not None


def settings_of(tag_policy: models.BackupTagPolicy) -> Dict[str, Any]:
    try:
        value = json.loads(tag_policy.settings or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(text: Optional[str]) -> List[str]:
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return list(value) if isinstance(value, list) else []


def policy_settings(policy: models.BackupPolicy) -> Dict[str, Any]:
    """A policy's current values, in the shape a tag policy stores."""
    out: Dict[str, Any] = {key: getattr(policy, key) for key in SCALARS}
    out.update({key: getattr(policy, key) or 0 for key in COUNTS})
    out.update({key: _json_list(getattr(policy, key)) for key in LISTS})
    return out


def _wanted(settings: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {key: settings.get(key) for key in SCALARS}
    out.update({key: settings.get(key) or 0 for key in COUNTS})
    out.update({key: list(settings.get(key) or []) for key in LISTS})
    return out


def apply_settings(policy: models.BackupPolicy, settings: Dict[str, Any]) -> bool:
    """Put ``settings`` on ``policy``; True when anything changed."""
    wanted = _wanted(settings)
    if policy_settings(policy) == wanted:
        return False
    for key in SCALARS:
        setattr(policy, key, wanted[key])
    for key in COUNTS:
        setattr(policy, key, wanted[key] or None)
    for key in LISTS:
        setattr(policy, key, json.dumps(wanted[key]))
    policy.updated_at = jobs.now()
    return True


def covering(db: Session) -> Dict[str, models.BackupTagPolicy]:
    """``{host id: the tag policy that wins for it}`` over the enabled tag
    policies."""
    rows = (
        db.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.enabled.is_(True))
        .order_by(
            models.BackupTagPolicy.priority,
            models.BackupTagPolicy.created_at,
            models.BackupTagPolicy.name,
        )
        .all()
    )
    winners: Dict[str, models.BackupTagPolicy] = {}
    for tag_policy in rows:
        host_ids = (
            db.query(models.HostTag.host_id)
            .filter(models.HostTag.tag_id == tag_policy.tag_id)
            .all()
        )
        for (host_id,) in host_ids:
            winners.setdefault(str(host_id), tag_policy)
    return winners


def winner_for(db: Session, host_id: Any) -> Optional[models.BackupTagPolicy]:
    """The enabled tag policy that would govern one host, by the same order
    ``covering`` uses (priority, then age, then name), or None."""
    return (
        db.query(models.BackupTagPolicy)
        .join(models.HostTag, models.HostTag.tag_id == models.BackupTagPolicy.tag_id)
        .filter(
            models.HostTag.host_id == host_id,
            models.BackupTagPolicy.enabled.is_(True),
        )
        .order_by(
            models.BackupTagPolicy.priority,
            models.BackupTagPolicy.created_at,
            models.BackupTagPolicy.name,
        )
        .first()
    )


@dataclass
class Outcome:
    """What one ``resolve`` pass did, for the API and the logs."""

    applied: List[Dict[str, Any]] = field(default_factory=list)
    unchanged: int = 0
    removed: List[Dict[str, Any]] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)

    def changed(self) -> bool:
        return bool(self.applied or self.removed)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "skipped": self.skipped,
        }


def _audit(db: Session, actor: Any, host: models.Host, text: str, details) -> None:
    AuditService.log(
        db=db,
        user_id=getattr(actor, "id", None),
        username=getattr(actor, "userid", None) or jobs.SYSTEM_ACTOR,
        action_type=ActionType.UPDATE,
        entity_type=EntityType.HOST,
        entity_id=str(host.id),
        entity_name=host.fqdn,
        description=text,
        details=details,
        commit=False,
    )


def _skip_reason(db: Session, host: Optional[models.Host]) -> str:
    if host is None:
        return "no_host"
    if not jobs.equipped(host)[0]:
        return "not_equipped"
    return reach.UNREACHABLE if reach.blocked(db, host) else ""


def _new_policy(db, host, target, actor) -> models.BackupPolicy:
    policy = models.BackupPolicy(
        host_id=host.id,
        target_id=target.id,
        config_version=1,
        host_acked_version=0,
        storage_acked_version=0,
        created_at=jobs.now(),
        created_by=getattr(actor, "userid", None) or jobs.SYSTEM_ACTOR,
    )
    db.add(policy)
    return policy


def _apply_one(db, host, tag_policy, target, actor, outcome: Outcome) -> None:
    policy = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )
    if policy is not None and policy.tag_policy_id is None:
        return  # the host's own policy wins (Configure)
    if policy is None:
        reason = _skip_reason(db, host)
        if reason:
            outcome.skipped.append(
                {"host_id": str(host.id), "fqdn": host.fqdn, "reason": reason}
            )
            return
        policy = _new_policy(db, host, target, actor)
    moved = str(policy.tag_policy_id or "") != str(tag_policy.id)
    changed = apply_settings(policy, settings_of(tag_policy))
    if not (moved or changed):
        outcome.unchanged += 1
        return
    if policy.id is not None and policy.host_acked_version:
        policy.config_version += 1
    policy.tag_policy_id = tag_policy.id
    outcome.applied.append(
        {"host_id": str(host.id), "fqdn": host.fqdn, "tag_policy": tag_policy.name}
    )
    _audit(
        db,
        actor,
        host,
        "Backup policy set from tag policy",
        {"tag_policy": tag_policy.name, "priority": tag_policy.priority},
    )


def _remove_uncovered(db, winners, actor, outcome: Outcome) -> None:
    """A host no enabled tag policy covers keeps the policy a tag gave it as
    its own, paused -- unless that tag policy still exists and is only
    switched off: switching one off pauses it (its hosts keep running what it
    last gave them)."""
    paused = {
        str(row_id)
        for (row_id,) in db.query(models.BackupTagPolicy.id)
        .filter(models.BackupTagPolicy.enabled.is_(False))
        .all()
    }
    stale = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.tag_policy_id.isnot(None))
        .all()
    )
    for policy in stale:
        if str(policy.host_id) in winners or str(policy.tag_policy_id) in paused:
            continue
        host = db.query(models.Host).filter(models.Host.id == policy.host_id).first()
        if host is not None:
            _audit(
                db,
                actor,
                host,
                "Backup policy paused (no tag policy covers this host any more); "
                "its settings, keys and history are kept as the host's own",
                {},
            )
        outcome.removed.append(
            {"host_id": str(policy.host_id), "fqdn": host.fqdn if host else None}
        )
        policy.tag_policy_id = None
        policy.enabled = False
        policy.config_version += 1


def resolve(db: Session, actor: Any = None) -> Outcome:
    """Bring every tag-covered host's policy to its winning tag policy, and
    drop the tag-given policies no tag policy covers any more."""
    outcome = Outcome()
    target = jobs.the_target(db)
    if target is None or not engine_loaded():
        return outcome
    winners = covering(db)
    for host_id, tag_policy in winners.items():
        host = db.query(models.Host).filter(models.Host.id == host_id).first()
        if host is None:
            continue
        _apply_one(db, host, tag_policy, target, actor, outcome)
    _remove_uncovered(db, winners, actor, outcome)
    db.flush()
    if outcome.changed():
        logger.info(
            "Backup tag policies: %d applied, %d removed, %d skipped",
            len(outcome.applied),
            len(outcome.removed),
            len(outcome.skipped),
        )
    return outcome


def source_of(db: Session, policy: Optional[models.BackupPolicy]) -> Dict[str, Any]:
    """Where a host's backup settings come from, for its card: this host's
    own policy, or a tag policy by name and priority."""
    if policy is None:
        return {"kind": "none"}
    if policy.tag_policy_id is None:
        own: Dict[str, Any] = {"kind": "own"}
        winner = winner_for(db, policy.host_id) if engine_loaded() else None
        if winner is not None:
            # A tag policy covers this host but its own policy wins: the
            # card offers "Use the tag policy".
            own["tag_policy_available"] = {
                "id": str(winner.id),
                "name": winner.name,
                "priority": winner.priority,
            }
        return own
    tag_policy = (
        db.query(models.BackupTagPolicy)
        .filter(models.BackupTagPolicy.id == policy.tag_policy_id)
        .first()
    )
    if tag_policy is None:
        return {"kind": "own"}
    return {
        "kind": "tag",
        "id": str(tag_policy.id),
        "name": tag_policy.name,
        "priority": tag_policy.priority,
    }


class HandoverRefused(Exception):
    """A host cannot be handed to the tag policies; ``code`` says why."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _own_policy_and_winner(db: Session, host: models.Host):
    """(the host's own policy, the tag policy that would govern it), or
    HandoverRefused.  Only a host on its OWN policy can be handed over: a
    tag-given one already follows the tags, and a host with no policy gets
    one from the resolver without any handover."""
    policy = (
        db.query(models.BackupPolicy)
        .filter(models.BackupPolicy.host_id == host.id)
        .first()
    )
    if policy is None:
        raise HandoverRefused("no_policy", "no_policy")
    if policy.tag_policy_id is not None:
        raise HandoverRefused("already_tag", "already_tag")
    winner = winner_for(db, host.id)
    if winner is None:
        raise HandoverRefused("not_covered", "not_covered")
    return policy, winner


def handover_changes(policy: models.BackupPolicy, winner) -> List[Dict[str, Any]]:
    """The host settings the tag policy would replace: ``{key, from, to}``."""
    current = policy_settings(policy)
    wanted = _wanted(settings_of(winner))
    return [
        {"key": key, "from": current[key], "to": wanted[key]}
        for key in (*SCALARS, *COUNTS, *LISTS)
        if current[key] != wanted[key]
    ]


def handover_preview(db: Session, host: models.Host) -> Dict[str, Any]:
    """What "Use the tag policy" would do to this host -- for the
    confirmation, which names the rule and every setting it replaces."""
    policy, winner = _own_policy_and_winner(db, host)
    return {
        "tag_policy": {
            "id": str(winner.id),
            "name": winner.name,
            "priority": winner.priority,
        },
        "changes": handover_changes(policy, winner),
    }


def use_tag_policy(db: Session, host: models.Host, actor: Any) -> Dict[str, Any]:
    """Hand a host on its own policy back to the tag policies WITHOUT
    removing its policy (2026-11-03): until now the only way back was to
    delete the policy, which orphans an encrypted host's keys and its
    repository.  Only the settings a tag policy controls change; the
    repository, encryption (keys, key rows, the repository before an
    encrypted one), snapshots, run history and the storage side's state are
    the row's own and stay as they are."""
    policy, winner = _own_policy_and_winner(db, host)
    changes = handover_changes(policy, winner)
    apply_settings(policy, settings_of(winner))
    policy.tag_policy_id = winner.id
    if policy.host_acked_version and changes:
        policy.config_version += 1  # the hosts get the new job files
    _audit(
        db,
        actor,
        host,
        "Backup policy handed to its tag policy",
        {
            "tag_policy": winner.name,
            "priority": winner.priority,
            "replaced": [change["key"] for change in changes],
        },
    )
    db.flush()
    return {
        "tag_policy": {
            "id": str(winner.id),
            "name": winner.name,
            "priority": winner.priority,
        },
        "changes": changes,
        "source": source_of(db, policy),
    }
