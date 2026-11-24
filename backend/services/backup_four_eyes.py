# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Four-eyes approval (ROADMAP 27.2, Enterprise ``backup_ops_engine``).

With the tenant's setting on (off by default -- a one-admin site must never be
locked out of its own restores), a restore over a host's own files is held as
a ``backup_restore_request`` until a second person with the restore role
approves it; a restore into staging and a preview are never held.  The
approval sends exactly the restore that was asked for
(``backups_restore_flow.perform``).  The engine decides who may do what and
when a request has expired; without the engine nothing is held and nothing
can be approved.

Since 2026-11-24 a request has a ``kind``: ``restore`` is built in; a
rebuild, a clone, a wipe or a migration registers its own (``register``)
with the role that may approve it and what approving it does, and is held
by the same table, rules and card.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import config, settings_service
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.tenant_context import get_active_tenant
from backend.services import backup_jobs as jobs
from backend.services.audit_service import EntityType

ENGINE = "backup_ops_engine"
SETTING = "backup_four_eyes"
AWAITING = "awaiting_approval"
RESTORE = "restore"


@dataclass(frozen=True)
class Kind:
    """One kind of held request.  ``role``: the SecurityRoles value an
    approver needs; ``perform(db, user, request, host)``: what approving it
    does, returning the run it started (``{"id": ...}``); ``refusals``: the
    API's messages by refusal code, for this kind."""

    role: str
    perform: Callable[..., Dict[str, Any]]
    refusals: Dict[str, Callable[[], str]]


KINDS: Dict[str, Kind] = {}


def register(name: str, kind: Kind) -> None:
    KINDS[name] = kind


def kind_of(request) -> str:
    return getattr(request, "kind", None) or RESTORE


def _iso(when) -> Optional[str]:
    return when.isoformat() if when is not None else None


def engine():
    """The loaded engine, or None -- also for one without four-eyes approval
    (an older build), which then holds nothing."""
    eng = module_loader.get_module(ENGINE)
    return eng if hasattr(eng, "restore_needs_approval") else None


def needs_approval(eng, kind: str, facts: Dict[str, Any]) -> bool:
    """The engine's rule for ``kind``; an engine from before kinds
    (``restore_needs_approval`` only) holds restores as it always did and
    every other kind whenever the setting is on."""
    on = enabled()
    if hasattr(eng, "needs_approval"):
        return bool(eng.needs_approval(kind, on, facts))
    if kind == RESTORE:
        return bool(
            eng.restore_needs_approval(on, facts.get("in_place"), facts.get("dry_run"))
        )
    return on and not facts.get("dry_run")


def _tenant() -> Optional[str]:
    return get_active_tenant() if config.is_multitenancy_enabled() else None


def enabled() -> bool:
    """The tenant's setting (off unless turned on)."""
    tenant_id = _tenant()
    if tenant_id:
        value = settings_service.get_tenant_setting(tenant_id, SETTING)
    else:
        value = settings_service.get_setting(SETTING)
    return value is True


def set_enabled(value: bool) -> None:
    tenant_id = _tenant()
    if tenant_id:
        settings_service.set_tenant_setting(tenant_id, SETTING, bool(value))
    else:
        settings_service.set_setting(SETTING, bool(value))


def hold_request(  # pylint: disable=too-many-arguments
    db: Session,
    current_user,
    host: models.Host,
    *,
    kind: str,
    payload: Dict[str, Any],
    facts: Dict[str, Any],
    audit_text: str,
    target: Optional[Dict[str, Any]] = None,
) -> Optional[Dict]:
    """Hold a request of ``kind`` for a second approver, or None to go
    ahead now.  ``payload`` is what approving it will run, exactly."""
    eng = engine()
    if eng is None or not needs_approval(eng, kind, facts):
        return None
    request = models.BackupRestoreRequest(
        host_id=host.id,
        kind=kind,
        body=json.dumps(payload),
        target=json.dumps(target) if target is not None else None,
        status="pending",
        requested_by=current_user.userid,
        requested_at=jobs.now(),
    )
    db.add(request)
    db.flush()
    # pylint: disable-next=import-outside-toplevel
    from backend.api.backups import _audit

    _audit(
        db,
        current_user,
        EntityType.HOST,
        host.id,
        host.fqdn,
        audit_text,
        {"request_id": str(request.id), "kind": kind, **payload},
    )
    db.commit()
    return {"status": AWAITING, "request_id": str(request.id), "kind": kind}


def hold(db: Session, current_user, host: models.Host, body) -> Optional[Dict]:
    """Hold this restore for a second approver, or None to send it now."""
    held = hold_request(
        db,
        current_user,
        host,
        kind=RESTORE,
        payload=body.model_dump(),
        facts={"in_place": body.in_place, "dry_run": body.dry_run},
        audit_text="Restore over the host's files requested; waits for a second approver",
    )
    if held is not None:
        held.update({"in_place": True, "staging_path": None})
    return held


def _as_dict(eng, request, host, now) -> Dict[str, Any]:
    body = json.loads(request.body)
    target = json.loads(request.target) if getattr(request, "target", None) else None
    return {
        "id": str(request.id),
        "kind": kind_of(request),
        "target": target,
        "host_id": str(request.host_id),
        "fqdn": host.fqdn if host is not None else None,
        "status": eng.request_state(
            {"status": request.status, "requested_at": request.requested_at}, now
        ),
        "snapshot": body.get("snapshot"),
        "include": body.get("include") or [],
        "packages": bool(body.get("packages")),
        "requested_by": request.requested_by,
        "requested_at": _iso(request.requested_at),
        "decided_by": request.decided_by,
        "decided_at": _iso(request.decided_at),
        "reason": request.reason,
        "run_id": str(request.run_id) if request.run_id else None,
    }


def recent(db: Session, eng, now, limit: int = 50) -> List[Dict[str, Any]]:
    """Pending requests first, then the latest decided ones; a pending one
    past its time is shown (and stored) as expired."""
    rows = (
        db.query(models.BackupRestoreRequest, models.Host)
        .outerjoin(models.Host, models.Host.id == models.BackupRestoreRequest.host_id)
        .order_by(models.BackupRestoreRequest.requested_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for request, host in rows:
        view = _as_dict(eng, request, host, now)
        if view["status"] == "expired" and request.status == "pending":
            request.status, request.decided_at = "expired", now
        out.append(view)
    db.commit()
    out.sort(key=lambda r: (r["status"] != "pending", r["requested_at"] or ""))
    return out


def _facts(request) -> Dict[str, Any]:
    return {
        "status": request.status,
        "requested_by": request.requested_by,
        "requested_at": request.requested_at,
    }


def approval_refusal(eng, request, user, now) -> Optional[str]:
    from backend.security.roles import (  # pylint: disable=import-outside-toplevel
        SecurityRoles,
    )

    kind = KINDS.get(kind_of(request))
    role = kind.role if kind is not None else SecurityRoles.RESTORE_FILES
    return eng.approval_refusal(_facts(request), user.userid, user.has_role(role), now)


def withdraw_refusal(eng, request, user, now) -> Optional[str]:
    return eng.withdraw_refusal(_facts(request), user.userid, now)
