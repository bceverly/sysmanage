"""
Federation policy management service (Phase 12.1.F).

CRUD + per-site assignment + push-status tracking for the centrally-
defined policies the coordinator distributes to sites.  Pro+ engine
wraps these as ``/api/v1/federation/policies*`` endpoints.

Polymorphic by ``policy_type`` (``update_profile``, ``firewall_role``,
``compliance_baseline``, …) — the type-specific body is JSON in
``definition_json``.  Validation of the body shape is the engine's
job (it knows what an update_profile looks like vs a firewall_role);
the service layer just stores opaque JSON.

Assignment + push semantics:

  * ``assign_policy_to_sites`` is idempotent — re-assigning the same
    (policy, site) doesn't error, it just resets ``push_status='pending'``
    so the next push cycle re-pushes after the operator edited the
    policy body.
  * ``mark_policy_pushed`` records the ``pushed_version`` so the
    coordinator can detect "policy was edited; needs re-push" without
    re-pushing every cycle.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.services import federation_retry_policy as retry_policy
from backend.persistence.models.federation import (
    FederationAuditLog,
    FederationPolicy,
    FederationPolicyAssignment,
    FederationSite,
)

# ---------------------------------------------------------------------
# Status constants — mirrored in the engine + UI to avoid string typos.
# ---------------------------------------------------------------------

PUSH_STATUS_PENDING = "pending"
PUSH_STATUS_PUSHED = "pushed"
PUSH_STATUS_ACKNOWLEDGED = "acknowledged"
PUSH_STATUS_ERROR = "error"
# Phase 12.10 hardening: terminal "give up" state.  An assignment
# is moved here when ``push_attempts >= retry_policy.MAX_ATTEMPTS``;
# the push worker excludes ``dead`` rows from
# ``list_all_pending_pushes`` so they don't get retried every tick.
# Operator intervention (re-assignment via ``assign_policy_to_sites``)
# resets to ``pending`` and clears the counter for a fresh window.
PUSH_STATUS_DEAD = "dead"

# Audit-log operation codes.
AUDIT_OP_POLICY_CREATED = "policy_created"
AUDIT_OP_POLICY_UPDATED = "policy_updated"
AUDIT_OP_POLICY_DEACTIVATED = "policy_deactivated"
AUDIT_OP_POLICY_ASSIGNED = "policy_assigned"
AUDIT_OP_POLICY_UNASSIGNED = "policy_unassigned"
AUDIT_OP_POLICY_PUSHED = "policy_pushed"
AUDIT_OP_POLICY_PUSH_FAILED = "policy_push_failed"


# ---------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------


class FederationPolicyError(Exception):
    """Base class for policy-service errors."""


class PolicyNotFoundError(FederationPolicyError, LookupError):
    """Raised when a policy_id doesn't resolve."""


class PolicyNameConflictError(FederationPolicyError, ValueError):
    """Raised when (policy_type, name) is taken by another policy."""


class PolicyAssignmentNotFoundError(FederationPolicyError, LookupError):
    """Raised when a (policy_id, site_id) assignment doesn't exist."""


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _ensure_policy(session: Session, policy_id: Any) -> FederationPolicy:
    uid = _coerce_uuid(policy_id)
    policy = session.get(FederationPolicy, uid)
    if policy is None:
        raise PolicyNotFoundError(f"No federation policy with id={uid}")
    return policy


def _ensure_site(session: Session, site_id: Any) -> FederationSite:
    uid = _coerce_uuid(site_id)
    site = session.get(FederationSite, uid)
    if site is None:
        raise LookupError(f"No federation site with id={uid}")
    return site


def _log_audit(
    session: Session,
    operation: str,
    *,
    actor_userid: Optional[str] = None,
    target_site_id: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None,
) -> FederationAuditLog:
    entry = FederationAuditLog(
        operation=operation,
        actor_userid=actor_userid,
        target_site_id=(
            _coerce_uuid(target_site_id) if target_site_id is not None else None
        ),
        details_json=json.dumps(details) if details else None,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------


def create_policy(
    session: Session,
    *,
    policy_type: str,
    name: str,
    definition: Dict[str, Any],
    description: Optional[str] = None,
    created_by: Optional[str] = None,
) -> FederationPolicy:
    """Create a new policy of ``policy_type`` named ``name``.

    ``definition`` is serialized to JSON.  The (type, name) pair is
    unique — re-creating a policy with the same name under the same
    type raises :class:`PolicyNameConflictError`.
    """
    if not policy_type or not policy_type.strip():
        raise ValueError("policy_type is required")
    if not name or not name.strip():
        raise ValueError("policy name is required")
    if not isinstance(definition, dict):
        raise ValueError("definition must be a dict (will be JSON-serialised)")

    policy_type = policy_type.strip()
    name = name.strip()

    existing = (
        session.execute(
            select(FederationPolicy).where(
                FederationPolicy.policy_type == policy_type,
                FederationPolicy.name == name,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise PolicyNameConflictError(
            f"A '{policy_type}' policy named '{name}' already exists"
        )

    policy = FederationPolicy(
        policy_type=policy_type,
        name=name,
        description=description,
        definition_json=json.dumps(definition, sort_keys=True),
        version=1,
        created_by=created_by,
        is_active=True,
    )
    session.add(policy)
    session.flush()

    _log_audit(
        session,
        AUDIT_OP_POLICY_CREATED,
        actor_userid=created_by,
        details={
            "policy_id": str(policy.id),
            "policy_type": policy_type,
            "name": name,
        },
    )
    return policy


def get_policy(session: Session, policy_id: Any) -> FederationPolicy:
    """Fetch a policy by id; raises :class:`PolicyNotFoundError` on miss."""
    return _ensure_policy(session, policy_id)


def list_policies(
    session: Session,
    *,
    policy_type: Optional[str] = None,
    active_only: bool = True,
) -> List[FederationPolicy]:
    """List policies, optionally filtered by type and active state."""
    stmt = select(FederationPolicy)
    if policy_type is not None:
        stmt = stmt.where(FederationPolicy.policy_type == policy_type)
    if active_only:
        stmt = stmt.where(FederationPolicy.is_active.is_(True))
    stmt = stmt.order_by(FederationPolicy.policy_type, FederationPolicy.name)
    return list(session.execute(stmt).scalars().all())


# Whitelist for ``update_policy`` — same approach as
# ``federation_site_service.update_site``.
_UPDATABLE_FIELDS = frozenset({"name", "description", "definition"})


def update_policy(
    session: Session,
    policy_id: Any,
    *,
    actor_userid: Optional[str] = None,
    **fields: Any,
) -> FederationPolicy:
    """Patch a policy's editable fields.  Bumps ``version`` if anything
    actually changes — assigned sites will pick up the new version
    on the next push cycle.
    """
    policy = _ensure_policy(session, policy_id)
    if not policy.is_active:
        raise ValueError(
            f"Policy {policy.id} is deactivated; reactivate before editing"
        )

    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown / non-updatable policy fields: {sorted(unknown)}")

    changes: Dict[str, Any] = {}

    if "name" in fields:
        new_name = fields["name"]
        if new_name != policy.name:
            # Uniqueness check against the same policy_type.
            collision = (
                session.execute(
                    select(FederationPolicy).where(
                        FederationPolicy.policy_type == policy.policy_type,
                        FederationPolicy.name == new_name,
                        FederationPolicy.id != policy.id,
                    )
                )
                .scalars()
                .first()
            )
            if collision is not None:
                raise PolicyNameConflictError(
                    f"A '{policy.policy_type}' policy named '{new_name}' "
                    f"already exists"
                )
            policy.name = new_name
            changes["name"] = new_name

    if "description" in fields and fields["description"] != policy.description:
        policy.description = fields["description"]
        changes["description"] = fields["description"]

    if "definition" in fields:
        new_def = fields["definition"]
        if not isinstance(new_def, dict):
            raise ValueError("definition must be a dict")
        new_json = json.dumps(new_def, sort_keys=True)
        if new_json != policy.definition_json:
            policy.definition_json = new_json
            changes["definition_changed"] = True

    if changes:
        policy.version += 1
        _log_audit(
            session,
            AUDIT_OP_POLICY_UPDATED,
            actor_userid=actor_userid,
            details={
                "policy_id": str(policy.id),
                "new_version": policy.version,
                "changes": list(changes.keys()),
            },
        )
    return policy


def deactivate_policy(
    session: Session,
    policy_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> FederationPolicy:
    """Mark a policy inactive.  Sites learn of the deactivation on
    the next push cycle and stop applying it.  The row + assignments
    are preserved for audit."""
    policy = _ensure_policy(session, policy_id)
    if not policy.is_active:
        return policy  # idempotent
    policy.is_active = False
    _log_audit(
        session,
        AUDIT_OP_POLICY_DEACTIVATED,
        actor_userid=actor_userid,
        details={"policy_id": str(policy.id), "name": policy.name},
    )
    return policy


# ---------------------------------------------------------------------
# Policy assignment
# ---------------------------------------------------------------------


def assign_policy_to_sites(
    session: Session,
    policy_id: Any,
    site_ids: Sequence[Any],
    *,
    assigned_by: Optional[str] = None,
) -> List[FederationPolicyAssignment]:
    """Assign ``policy_id`` to one or more sites.

    Idempotent — re-assigning resets ``push_status='pending'`` so
    the operator can force a re-push without removing + re-adding.
    """
    policy = _ensure_policy(session, policy_id)
    if not policy.is_active:
        raise ValueError(f"Policy {policy.id} is deactivated; cannot assign to sites")

    assignments: List[FederationPolicyAssignment] = []
    for raw_site_id in site_ids:
        site = _ensure_site(session, raw_site_id)
        existing = (
            session.execute(
                select(FederationPolicyAssignment).where(
                    FederationPolicyAssignment.policy_id == policy.id,
                    FederationPolicyAssignment.site_id == site.id,
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            assignment = FederationPolicyAssignment(
                policy_id=policy.id,
                site_id=site.id,
                assigned_by=assigned_by,
                push_status=PUSH_STATUS_PENDING,
            )
            session.add(assignment)
        else:
            # Re-assignment is a "re-push intent" — reset status AND
            # reset the retry counter so a previously dead-lettered
            # assignment gets a fresh exponential-backoff window.
            existing.push_status = PUSH_STATUS_PENDING
            existing.last_push_error = None
            existing.push_attempts = 0
            existing.assigned_by = assigned_by
            existing.assigned_at = _utcnow_naive()
            assignment = existing
        assignments.append(assignment)
        _log_audit(
            session,
            AUDIT_OP_POLICY_ASSIGNED,
            actor_userid=assigned_by,
            target_site_id=site.id,
            details={
                "policy_id": str(policy.id),
                "name": policy.name,
            },
        )
    return assignments


def unassign_policy_from_site(
    session: Session,
    policy_id: Any,
    site_id: Any,
    *,
    actor_userid: Optional[str] = None,
) -> bool:
    """Remove the (policy, site) assignment.  Returns True if a row
    was deleted, False if nothing was assigned in the first place."""
    pid = _coerce_uuid(policy_id)
    sid = _coerce_uuid(site_id)
    assignment = (
        session.execute(
            select(FederationPolicyAssignment).where(
                and_(
                    FederationPolicyAssignment.policy_id == pid,
                    FederationPolicyAssignment.site_id == sid,
                )
            )
        )
        .scalars()
        .first()
    )
    if assignment is None:
        return False
    session.delete(assignment)
    _log_audit(
        session,
        AUDIT_OP_POLICY_UNASSIGNED,
        actor_userid=actor_userid,
        target_site_id=sid,
        details={"policy_id": str(pid)},
    )
    return True


def list_assignments_for_policy(
    session: Session, policy_id: Any
) -> List[FederationPolicyAssignment]:
    """Every site this policy is assigned to, with push-status."""
    pid = _coerce_uuid(policy_id)
    return list(
        session.execute(
            select(FederationPolicyAssignment).where(
                FederationPolicyAssignment.policy_id == pid
            )
        )
        .scalars()
        .all()
    )


def list_assignments_for_site(
    session: Session, site_id: Any
) -> List[FederationPolicyAssignment]:
    """Every policy assigned to this site, with push-status."""
    sid = _coerce_uuid(site_id)
    return list(
        session.execute(
            select(FederationPolicyAssignment).where(
                FederationPolicyAssignment.site_id == sid
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------
# Push status tracking
# ---------------------------------------------------------------------


def mark_policy_pushed(
    session: Session,
    policy_id: Any,
    site_id: Any,
    *,
    pushed_version: int,
) -> FederationPolicyAssignment:
    """Record a successful push to ``site_id``.

    Stores the version that was actually delivered so the coordinator
    can detect "policy edited; sites need a re-push" by comparing
    ``policy.version > assignment.pushed_version``.
    """
    pid = _coerce_uuid(policy_id)
    sid = _coerce_uuid(site_id)
    assignment = (
        session.execute(
            select(FederationPolicyAssignment).where(
                and_(
                    FederationPolicyAssignment.policy_id == pid,
                    FederationPolicyAssignment.site_id == sid,
                )
            )
        )
        .scalars()
        .first()
    )
    if assignment is None:
        raise PolicyAssignmentNotFoundError(
            f"No assignment for policy={pid} site={sid}"
        )
    assignment.push_status = PUSH_STATUS_PUSHED
    assignment.last_push_attempt_at = _utcnow_naive()
    assignment.last_push_error = None
    assignment.pushed_version = pushed_version
    _log_audit(
        session,
        AUDIT_OP_POLICY_PUSHED,
        target_site_id=sid,
        details={
            "policy_id": str(pid),
            "pushed_version": pushed_version,
        },
    )
    return assignment


def mark_policy_push_failed(
    session: Session,
    policy_id: Any,
    site_id: Any,
    *,
    error: str,
) -> FederationPolicyAssignment:
    """Record a failed push attempt.  Leaves ``pushed_version`` unchanged
    so a future success-then-fail sequence still tracks the last
    known-good version."""
    pid = _coerce_uuid(policy_id)
    sid = _coerce_uuid(site_id)
    assignment = (
        session.execute(
            select(FederationPolicyAssignment).where(
                and_(
                    FederationPolicyAssignment.policy_id == pid,
                    FederationPolicyAssignment.site_id == sid,
                )
            )
        )
        .scalars()
        .first()
    )
    if assignment is None:
        raise PolicyAssignmentNotFoundError(
            f"No assignment for policy={pid} site={sid}"
        )
    assignment.push_attempts = (assignment.push_attempts or 0) + 1
    assignment.last_push_attempt_at = _utcnow_naive()
    assignment.last_push_error = error
    # Dead-letter transition: after MAX_ATTEMPTS failures, stop
    # retrying.  Operator can re-assign to reset the counter via
    # ``assign_policy_to_sites``.
    if retry_policy.is_dead_lettered(assignment.push_attempts):
        assignment.push_status = PUSH_STATUS_DEAD
    else:
        assignment.push_status = PUSH_STATUS_ERROR
    _log_audit(
        session,
        AUDIT_OP_POLICY_PUSH_FAILED,
        target_site_id=sid,
        details={"policy_id": str(pid), "error": error},
    )
    return assignment


def list_pending_push_targets(
    session: Session, policy_id: Any
) -> List[FederationPolicyAssignment]:
    """Assignments needing a push for this policy.

    Includes both ``pending`` rows (never pushed) AND rows whose
    ``pushed_version`` is behind the policy's current version (stale).
    """
    policy = _ensure_policy(session, policy_id)
    return list(
        session.execute(
            select(FederationPolicyAssignment).where(
                and_(
                    FederationPolicyAssignment.policy_id == policy.id,
                    # Either never pushed, OR stale version.
                    (
                        (FederationPolicyAssignment.push_status != PUSH_STATUS_PUSHED)
                        | (FederationPolicyAssignment.pushed_version < policy.version)
                    ),
                )
            )
        )
        .scalars()
        .all()
    )


def list_all_pending_pushes(
    session: Session,
    *,
    now: Optional[datetime] = None,
) -> List[Tuple[FederationPolicy, FederationPolicyAssignment]]:
    """Cross-policy variant for the coordinator's push worker.

    Returns every ``(policy, assignment)`` pair where the assignment
    needs delivery — either never pushed, or its ``pushed_version`` is
    behind the policy's current version.  ``is_active=False`` policies
    are skipped (deactivation should prevent further pushes).  Joins
    in a single query so the worker doesn't N+1 the policy table.

    Phase 12.10 hardening: assignments in their backoff window
    (after a failed push attempt) are skipped, and assignments
    whose ``push_attempts >= MAX_ATTEMPTS`` are excluded entirely
    via the ``PUSH_STATUS_DEAD`` check — the operator must re-
    assign the policy to give them a fresh window.  ``now`` is
    injectable for deterministic tests.
    """
    if now is None:
        now = _utcnow_naive()
    rows = list(
        session.execute(
            select(FederationPolicy, FederationPolicyAssignment)
            .join(
                FederationPolicyAssignment,
                FederationPolicyAssignment.policy_id == FederationPolicy.id,
            )
            .where(
                and_(
                    FederationPolicy.is_active.is_(True),
                    FederationPolicyAssignment.push_status != PUSH_STATUS_DEAD,
                    (
                        (FederationPolicyAssignment.push_status != PUSH_STATUS_PUSHED)
                        | (
                            FederationPolicyAssignment.pushed_version
                            < FederationPolicy.version
                        )
                    ),
                )
            )
        ).all()
    )
    # Backoff gate.  Done in Python so the formula stays one place
    # (``retry_policy.compute_backoff``) and so jitter doesn't
    # bleed into the SQL plan.
    return [
        (policy, assignment)
        for policy, assignment in rows
        if retry_policy.is_ready_for_retry(
            assignment.last_push_attempt_at,
            assignment.push_attempts,
            now,
        )
    ]
