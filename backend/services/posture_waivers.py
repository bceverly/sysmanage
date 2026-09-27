# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Waivers: an accepted risk as an AUDIT ARTIFACT (ROADMAP 21.4 S4).

A waiver says "we know this item is open and accept it", with who, when and
why -- written through ``audit_service`` like any other privileged action.
It is NEUTRAL, never a green tick: the item's evaluation keeps saying "open"
underneath, and the punch list shows "waived" only as an overlay. Revoking it
makes the item count as open again; revoked waivers are kept as history.

WHAT A WAIVER IS SCOPED TO (decided 2026-09-26)
-----------------------------------------------
The basis it was granted on: the rule's VERSION, the item's RISK, and the
values of the threat-model attributes the rule's ``applies_when`` reads. It
goes STALE -- the item counts as open again until an administrator
re-affirms it -- when the risk RISES, the rule version changes, or one of
those attributes changes. A lower or unchanged risk keeps it.

Only an OPEN item can be waived: waiving an item that could not be assessed
would hide a blind spot, and a satisfied item has nothing to accept.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.services.audit_service import ActionType, AuditService, EntityType

STALE_RISK_ROSE = "risk_rose"
STALE_RULE_CHANGED = "rule_version_changed"
STALE_BASIS_CHANGED = "threat_model_changed"


class WaiverError(ValueError):
    """A waiver request that cannot be honored; ``code`` names why."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def basis_attributes(
    rule: Dict[str, Any], attributes: Dict[str, Any]
) -> Dict[str, bool]:
    """The values of exactly the attributes the rule's applies_when reads."""
    kind, value = next(iter((rule.get("applies_when") or {"always": True}).items()))
    if kind == "always":
        return {}
    return {name: bool((attributes or {}).get(name)) for name in value}


def active_waiver(db, scope, rule_key) -> Optional[models.PostureWaiver]:
    return (
        db.query(models.PostureWaiver)
        .filter(
            models.PostureWaiver.scope_kind == scope["scope_kind"],
            models.PostureWaiver.scope_ref == scope["scope_ref"],
            models.PostureWaiver.rule_key == rule_key,
            models.PostureWaiver.revoked_at.is_(None),
        )
        .order_by(models.PostureWaiver.granted_at.desc())
        .first()
    )


def stale_reason(waiver, item, rule, attributes) -> Optional[str]:
    """Why ``waiver`` no longer covers ``item``, or None when it still does."""
    if item.rule_version != waiver.rule_version:
        return STALE_RULE_CHANGED
    if (item.risk or 0) > (waiver.risk or 0):
        return STALE_RISK_ROSE
    if basis_attributes(rule, attributes) != (waiver.basis_attributes or {}):
        return STALE_BASIS_CHANGED
    return None


def refresh_staleness(db, scope, item, rule, attributes, now=None) -> Optional[str]:
    """Mark the item's active waiver stale (or fresh again after a
    re-affirmation) against the current evaluation. Returns the reason.

    Staleness is only ever SET here, never silently cleared: once stale, a
    waiver needs an administrator to re-affirm it, even if the risk later
    falls back -- the acceptance was made about a different situation.
    """
    waiver = active_waiver(db, scope, item.rule_key)
    if waiver is None or item.state != models.POSTURE_OPEN:
        return None
    if waiver.stale_reason:
        return waiver.stale_reason
    reason = stale_reason(waiver, item, rule, attributes)
    if reason:
        waiver.stale_reason = reason
        waiver.stale_since = now or _now()
    return reason


def display_state(item, waiver) -> str:
    """The punch-list state: ``waived`` overlays an OPEN item under an active,
    non-stale waiver; everything else shows its evaluated state."""
    if (
        item.state == models.POSTURE_OPEN
        and waiver is not None
        and not waiver.stale_reason
    ):
        return models.POSTURE_WAIVED
    return item.state


def _audit(db, user, action, description, waiver, item) -> None:
    AuditService.log(
        db=db,
        action_type=action,
        entity_type=EntityType.POSTURE_WAIVER,
        description=description,
        user_id=getattr(user, "id", None),
        username=getattr(user, "userid", None),
        entity_id=str(waiver.id),
        entity_name=item.rule_key,
        details={
            "rule_key": item.rule_key,
            "reason": waiver.reason,
            "rule_version": waiver.rule_version,
            "risk": waiver.risk,
            "basis_attributes": waiver.basis_attributes,
            "threat_model_version": waiver.threat_model_version,
        },
        category="security",
    )


def grant(db, scope, item, rule, model, user, reason: str) -> models.PostureWaiver:
    """Waive an OPEN item. Raises WaiverError."""
    if not (reason or "").strip():
        raise WaiverError("reason_required")
    if item.state != models.POSTURE_OPEN:
        raise WaiverError("not_open")
    if active_waiver(db, scope, item.rule_key) is not None:
        raise WaiverError("already_waived")
    waiver = models.PostureWaiver(
        **scope,
        rule_key=item.rule_key,
        reason=reason.strip(),
        rule_version=item.rule_version,
        risk=item.risk,
        basis_attributes=basis_attributes(rule, model.attributes),
        threat_model_version=model.model_version,
        granted_by=user.userid,
        granted_at=_now(),
    )
    db.add(waiver)
    db.flush()
    _audit(
        db,
        user,
        ActionType.CREATE,
        f"Waived posture item {item.rule_key}",
        waiver,
        item,
    )
    return waiver


def revoke(db, scope, item, user) -> models.PostureWaiver:
    """Withdraw the active waiver: the item counts as open again."""
    waiver = active_waiver(db, scope, item.rule_key)
    if waiver is None:
        raise WaiverError("not_waived")
    waiver.revoked_at = _now()
    waiver.revoked_by = user.userid
    _audit(
        db,
        user,
        ActionType.DELETE,
        f"Revoked waiver for {item.rule_key}",
        waiver,
        item,
    )
    return waiver


def reaffirm(db, scope, item, rule, model, user, reason: Optional[str] = None):
    """Accept a STALE waiver again, against the CURRENT basis."""
    waiver = active_waiver(db, scope, item.rule_key)
    if waiver is None:
        raise WaiverError("not_waived")
    if not waiver.stale_reason:
        raise WaiverError("not_stale")
    if reason is not None and reason.strip():
        waiver.reason = reason.strip()
    waiver.rule_version = item.rule_version
    waiver.risk = item.risk
    waiver.basis_attributes = basis_attributes(rule, model.attributes)
    waiver.threat_model_version = model.model_version
    waiver.stale_reason = None
    waiver.stale_since = None
    waiver.reaffirmed_by = user.userid
    waiver.reaffirmed_at = _now()
    _audit(
        db,
        user,
        ActionType.UPDATE,
        f"Re-affirmed waiver for {item.rule_key}",
        waiver,
        item,
    )
    return waiver
