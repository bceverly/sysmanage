"""Federation-aware dynamic-secret leases — coordinator side (Phase 12.5).

The coordinator owns the master OpenBAO/Vault.  Restricted sites never need
direct Vault access: a site requests a short-lived credential for one of its
hosts (the upstream ``secret_lease_request`` sync payload), the coordinator
issues it from the master Vault, and a SINGLE coordinator-side reconcile
loop renews / revokes / expires every site's leases — there are no per-site
sweepers because every lease lives in the one master Vault.

This module is the pure-Python bookkeeping the Pro+ ``secrets_engine`` /
``federation_controller_engine`` wraps:

  * the engine performs the actual Vault issue/renew/revoke I/O,
  * this service records the lifecycle in ``federation_secret_lease`` and
    answers "what needs issuing / renewing / expiring now?".

It NEVER stores the secret value — only the Vault ``lease_id`` (for
renew/revoke) and non-sensitive metadata.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import (
    FED_LEASE_ACTIVE,
    FED_LEASE_EXPIRED,
    FED_LEASE_FAILED,
    FED_LEASE_REQUESTED,
    FED_LEASE_REVOKED,
    FederationSecretLease,
)

# Terminal states are pruned by the retention sweep.
_TERMINAL_STATES = (FED_LEASE_REVOKED, FED_LEASE_EXPIRED, FED_LEASE_FAILED)
DEFAULT_LEASE_RETENTION_DAYS = 14


class FederationSecretLeaseError(Exception):
    """Base error for the federation secret-lease service."""


class LeaseNotFoundError(FederationSecretLeaseError, LookupError):
    """Raised when a lease id doesn't resolve."""


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _coerce_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _require(session: Session, lease_id: Any) -> FederationSecretLease:
    row = session.get(FederationSecretLease, _coerce_uuid(lease_id))
    if row is None:
        raise LeaseNotFoundError(f"No federation secret lease with id={lease_id}")
    return row


# ---------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------


def record_requested_lease(
    session: Session,
    *,
    site_id: Any,
    host_id: str,
    secret_name: str,
    backend_role: str,
    kind: str,
    ttl_seconds: Optional[int] = None,
    correlation_key: Optional[str] = None,
) -> FederationSecretLease:
    """Record a site's lease request (status ``requested``).

    The engine's issue pass later picks this up (``list_pending``), calls
    the master Vault, and transitions it via :func:`mark_issued` /
    :func:`mark_failed`.  Idempotent on ``correlation_key``: re-recording the
    same key returns the existing row rather than duplicating a request.
    Caller commits.
    """
    if not host_id or not secret_name or not backend_role or not kind:
        raise ValueError("host_id, secret_name, backend_role, kind are required")
    if correlation_key:
        existing = (
            session.execute(
                select(FederationSecretLease).where(
                    FederationSecretLease.correlation_key == correlation_key
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            return existing
    row = FederationSecretLease(
        site_id=_coerce_uuid(site_id),
        host_id=host_id,
        secret_name=secret_name,
        backend_role=backend_role,
        kind=kind,
        ttl_seconds=ttl_seconds,
        status=FED_LEASE_REQUESTED,
        correlation_key=correlation_key,
    )
    session.add(row)
    session.flush()
    return row


def mark_issued(
    session: Session,
    lease_id: Any,
    *,
    vault_lease_id: str,
    ttl_seconds: Optional[int] = None,
    expires_at: Optional[datetime] = None,
    secret_metadata: Optional[Dict[str, Any]] = None,
) -> FederationSecretLease:
    """Transition ``requested`` → ``active`` after the master Vault issued it.

    ``expires_at`` defaults to ``now + ttl_seconds`` when not supplied.
    Stores the Vault ``lease_id`` (needed to renew/revoke) and any
    non-sensitive metadata — never the secret value.
    """
    import json  # noqa: PLC0415

    row = _require(session, lease_id)
    now = _utcnow_naive()
    row.status = FED_LEASE_ACTIVE
    row.vault_lease_id = vault_lease_id
    row.issued_at = now
    row.last_error = None
    if ttl_seconds is not None:
        row.ttl_seconds = ttl_seconds
    if expires_at is not None:
        row.expires_at = expires_at
    elif row.ttl_seconds:
        row.expires_at = now + timedelta(seconds=row.ttl_seconds)
    if secret_metadata is not None:
        row.secret_metadata_json = json.dumps(secret_metadata, sort_keys=True)
    return row


def mark_failed(
    session: Session, lease_id: Any, *, error: str
) -> FederationSecretLease:
    """Record that a Vault issue/renew failed (terminal ``failed``)."""
    row = _require(session, lease_id)
    row.status = FED_LEASE_FAILED
    row.last_error = error
    return row


def mark_renewed(
    session: Session,
    lease_id: Any,
    *,
    expires_at: Optional[datetime] = None,
    ttl_seconds: Optional[int] = None,
) -> FederationSecretLease:
    """Record a successful Vault renewal — pushes ``expires_at`` out."""
    row = _require(session, lease_id)
    now = _utcnow_naive()
    row.last_renewed_at = now
    row.last_error = None
    if ttl_seconds is not None:
        row.ttl_seconds = ttl_seconds
    if expires_at is not None:
        row.expires_at = expires_at
    elif row.ttl_seconds:
        row.expires_at = now + timedelta(seconds=row.ttl_seconds)
    # A renew on an expired-but-not-yet-swept row revives it.
    if row.status in (FED_LEASE_ACTIVE, FED_LEASE_EXPIRED):
        row.status = FED_LEASE_ACTIVE
    return row


def mark_delivered(session: Session, lease_id: Any) -> FederationSecretLease:
    """Record that the issued/rotated secret reached the requesting site.

    A delivered lease drops out of the reconcile loop's rotation candidates
    until it next nears expiry."""
    row = _require(session, lease_id)
    row.delivered_at = _utcnow_naive()
    row.last_error = None
    return row


def mark_revoked(session: Session, lease_id: Any) -> FederationSecretLease:
    """Record a revocation (terminal ``revoked``)."""
    row = _require(session, lease_id)
    row.status = FED_LEASE_REVOKED
    row.revoked_at = _utcnow_naive()
    return row


# ---------------------------------------------------------------------
# Reads + the reconcile loop's work-lists
# ---------------------------------------------------------------------


def get_lease(session: Session, lease_id: Any) -> Optional[FederationSecretLease]:
    return session.get(FederationSecretLease, _coerce_uuid(lease_id))


def list_pending(session: Session, *, limit: int = 100) -> List[FederationSecretLease]:
    """Requested-but-not-yet-issued leases for the engine's issue pass."""
    return list(
        session.execute(
            select(FederationSecretLease)
            .where(FederationSecretLease.status == FED_LEASE_REQUESTED)
            .order_by(FederationSecretLease.requested_at)
            .limit(max(1, limit))
        )
        .scalars()
        .all()
    )


def list_expiring(
    session: Session,
    *,
    within_seconds: int,
    now: Optional[datetime] = None,
) -> List[FederationSecretLease]:
    """Active leases whose ``expires_at`` is within ``within_seconds`` — the
    reconcile loop's renew candidates.  Leases with no expiry are skipped."""
    now = now or _utcnow_naive()
    horizon = now + timedelta(seconds=within_seconds)
    return list(
        session.execute(
            select(FederationSecretLease)
            .where(
                and_(
                    FederationSecretLease.status == FED_LEASE_ACTIVE,
                    FederationSecretLease.expires_at.isnot(None),
                    FederationSecretLease.expires_at <= horizon,
                )
            )
            .order_by(FederationSecretLease.expires_at)
        )
        .scalars()
        .all()
    )


def list_rotation_candidates(
    session: Session,
    *,
    within_seconds: int,
    now: Optional[datetime] = None,
) -> List[FederationSecretLease]:
    """Active, already-issued leases that need a rotate+deliver pass.

    A candidate is either nearing expiry (``expires_at`` within
    ``within_seconds``) OR issued-but-not-yet-delivered (a site that was offline
    when the lease was first issued).  Both get a fresh credential generated and
    delivered: rotation before expiry, and recovery for a missed delivery.
    Leases without a Vault id (never successfully issued) are excluded."""
    now = now or _utcnow_naive()
    horizon = now + timedelta(seconds=within_seconds)
    return list(
        session.execute(
            select(FederationSecretLease)
            .where(
                and_(
                    FederationSecretLease.status == FED_LEASE_ACTIVE,
                    FederationSecretLease.vault_lease_id.isnot(None),
                    or_(
                        FederationSecretLease.delivered_at.is_(None),
                        and_(
                            FederationSecretLease.expires_at.isnot(None),
                            FederationSecretLease.expires_at <= horizon,
                        ),
                    ),
                )
            )
            .order_by(FederationSecretLease.expires_at)
        )
        .scalars()
        .all()
    )


def expire_overdue(session: Session, *, now: Optional[datetime] = None) -> int:
    """Mark active leases already past ``expires_at`` as ``expired``.

    Returns the count expired.  Run before the renew pass so a lease the
    coordinator couldn't renew in time doesn't linger as ``active``.
    """
    now = now or _utcnow_naive()
    rows = (
        session.execute(
            select(FederationSecretLease).where(
                and_(
                    FederationSecretLease.status == FED_LEASE_ACTIVE,
                    FederationSecretLease.expires_at.isnot(None),
                    FederationSecretLease.expires_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = FED_LEASE_EXPIRED
    if rows:
        session.flush()
    return len(rows)


def list_leases(
    session: Session,
    *,
    site_id: Any = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[FederationSecretLease]:
    """Operator-facing list, newest-first, optionally scoped by site/status."""
    stmt = select(FederationSecretLease)
    if site_id is not None:
        stmt = stmt.where(FederationSecretLease.site_id == _coerce_uuid(site_id))
    if status is not None:
        stmt = stmt.where(FederationSecretLease.status == status)
    stmt = stmt.order_by(FederationSecretLease.requested_at.desc()).limit(max(1, limit))
    return list(session.execute(stmt).scalars().all())


def prune_terminal(
    session: Session, *, older_than_days: int = DEFAULT_LEASE_RETENTION_DAYS
) -> int:
    """Delete terminal (revoked/expired/failed) leases older than the
    retention window.  Returns the count deleted.  Caller commits."""
    cutoff = _utcnow_naive() - timedelta(days=older_than_days)
    rows = (
        session.execute(
            select(FederationSecretLease).where(
                and_(
                    FederationSecretLease.status.in_(_TERMINAL_STATES),
                    FederationSecretLease.requested_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        session.delete(row)
    if rows:
        session.flush()
    return len(rows)


def to_dict(lease: FederationSecretLease) -> Dict[str, Any]:
    """Serialise a lease for the API (no secret value)."""
    import json  # noqa: PLC0415

    def _iso(dt):
        return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None

    return {
        "id": str(lease.id),
        "site_id": str(lease.site_id),
        "host_id": lease.host_id,
        "secret_name": lease.secret_name,
        "backend_role": lease.backend_role,
        "kind": lease.kind,
        "status": lease.status,
        "vault_lease_id": lease.vault_lease_id,
        "ttl_seconds": lease.ttl_seconds,
        "requested_at": _iso(lease.requested_at),
        "issued_at": _iso(lease.issued_at),
        "expires_at": _iso(lease.expires_at),
        "last_renewed_at": _iso(lease.last_renewed_at),
        "revoked_at": _iso(lease.revoked_at),
        "delivered_at": _iso(lease.delivered_at),
        "last_error": lease.last_error,
        "secret_metadata": (
            json.loads(lease.secret_metadata_json)
            if lease.secret_metadata_json
            else None
        ),
    }
