"""Federation-aware dynamic-secret leases — site side (Phase 12.5).

A subordinate site asks its coordinator for a short-lived credential on
behalf of one of its hosts.  Per the queue-everything rule this does NOT
call the coordinator directly — it ENQUEUES a ``secret_lease_request``
payload onto ``federation_sync_queue`` and the outbound tick ships it.  The
coordinator issues the lease from the master Vault and echoes the result
back down; the site records that echo in ``federation_received_secret_lease``
(the inbox) so the site engine can deliver the credential to the host
through the agent's secure channel.

The inbox row stores STATUS + non-sensitive metadata only — the secret value
is delivered transiently by the engine and never persisted here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models.federation import FederationReceivedSecretLease
from backend.services import federation_sync_queue_service as sync_svc

SECRET_LEASE_REQUEST_PAYLOAD_TYPE = (
    "secret_lease_request"  # nosec B105 - payload-type identifier, not a credential
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_correlation_key() -> str:
    """A fresh request/response correlation key (also the queue dedup key)."""
    return uuid.uuid4().hex


def enqueue_lease_request(
    session: Session,
    *,
    host_id: str,
    secret_name: str,
    backend_role: str,
    kind: str,
    ttl_seconds: Optional[int] = None,
    correlation_key: Optional[str] = None,
) -> str:
    """Queue an upstream lease request; returns its ``correlation_key``.

    The key dedups the queue entry (re-requesting the same key replaces the
    pending payload) and later matches the coordinator's result echo.
    Caller commits.
    """
    if not host_id or not secret_name or not backend_role or not kind:
        raise ValueError("host_id, secret_name, backend_role, kind are required")
    key = correlation_key or new_correlation_key()
    sync_svc.enqueue(
        session,
        payload_type=SECRET_LEASE_REQUEST_PAYLOAD_TYPE,
        payload={
            "correlation_key": key,
            "host_id": host_id,
            "secret_name": secret_name,
            "backend_role": backend_role,
            "kind": kind,
            "ttl_seconds": ttl_seconds,
        },
        dedup_key=f"secret_lease:{key}",
    )
    return key


def record_received_lease(
    session: Session,
    *,
    correlation_key: str,
    host_id: str,
    secret_name: str,
    status: str,
    secret_metadata: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> FederationReceivedSecretLease:
    """Record the coordinator's lease-result echo into the site inbox.

    Idempotent on ``correlation_key`` — a re-pushed result updates the
    existing inbox row rather than duplicating it.  Caller commits.
    """
    import json  # noqa: PLC0415

    existing = (
        session.execute(
            select(FederationReceivedSecretLease).where(
                FederationReceivedSecretLease.correlation_key == correlation_key
            )
        )
        .scalars()
        .first()
    )
    meta_json = (
        json.dumps(secret_metadata, sort_keys=True)
        if secret_metadata is not None
        else None
    )
    if existing is not None:
        existing.status = status
        existing.secret_metadata_json = meta_json
        existing.last_error = error
        return existing
    row = FederationReceivedSecretLease(
        correlation_key=correlation_key,
        host_id=host_id,
        secret_name=secret_name,
        status=status,
        secret_metadata_json=meta_json,
        last_error=error,
    )
    session.add(row)
    session.flush()
    return row


def list_undelivered(
    session: Session, *, limit: int = 100
) -> List[FederationReceivedSecretLease]:
    """Inbox rows the site engine still has to deliver to their hosts."""
    return list(
        session.execute(
            select(FederationReceivedSecretLease)
            .where(FederationReceivedSecretLease.delivered_at.is_(None))
            .order_by(FederationReceivedSecretLease.received_at)
            .limit(max(1, limit))
        )
        .scalars()
        .all()
    )


def mark_delivered(session: Session, received_id: Any) -> FederationReceivedSecretLease:
    """Mark an inbox row as delivered to its host."""
    row = session.get(FederationReceivedSecretLease, received_id)
    if row is None:
        raise LookupError(f"No received secret lease with id={received_id}")
    row.delivered_at = _utcnow_naive()
    return row
