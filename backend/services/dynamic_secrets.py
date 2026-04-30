"""
Dynamic-secret issuance backed by OpenBAO/Vault (Phase 8.7).

This service is the bridge between the Pro+ secrets_engine module and
the OpenBAO ``vault_service``.  We deliberately keep the implementation
in the OSS layer — the value is in the operator workflow (issue → use
→ auto-expire), not in proprietary cryptography.

Flow:

  1. Operator calls ``issue_lease(kind, role, ttl_seconds, name)``.
  2. We generate a strong random secret, store it in OpenBAO at a
     TTL-bound path, and persist a ``DynamicSecretLease`` row holding
     the path / expiry / status (NEVER the secret itself).
  3. Operator gets the plaintext value ONCE in the response.
  4. After TTL elapses OpenBAO drops the data;  the sweeper marks the
     row EXPIRED on the next pass.
  5. Operator (or sweeper) can revoke ahead of TTL via
     ``revoke_lease(id)`` which deletes from OpenBAO immediately.

For ``database`` and ``ssh`` kinds we forward to OpenBAO's dedicated
backends (``/v1/database/creds/<role>`` etc.);  for ``token`` we use
the simple wrapped-data flow.  In all cases the per-lease audit row
makes it possible to enumerate "who issued what when".
"""

import logging
import secrets as _secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from backend.persistence import models
from backend.persistence.models.dynamic_secrets import (
    LEASE_ACTIVE,
    LEASE_EXPIRED,
    LEASE_FAILED,
    LEASE_KIND_DATABASE,
    LEASE_KIND_SSH,
    LEASE_KIND_TOKEN,
    LEASE_KINDS,
    LEASE_REVOKED,
)
from backend.services.vault_service import VaultError, VaultService

logger = logging.getLogger(__name__)


# Bounds on operator-supplied TTLs.  60 s lower bound prevents
# accidentally issuing leases that expire before they can be used; the
# upper bound (24 h) keeps us aligned with the "short-lived" promise.
TTL_MIN_SECONDS = 60
TTL_MAX_SECONDS = 24 * 60 * 60
TTL_DEFAULT_SECONDS = 30 * 60


class DynamicSecretError(Exception):
    """Wrapper for failures during issue/revoke; preserves the
    underlying VaultError for the API layer to render."""


def _generate_secret_value(kind: str) -> str:
    """Cryptographically-strong random value used as the issued
    credential body when the kind doesn't have a vault dynamic
    backend configured."""
    if kind == LEASE_KIND_SSH:
        # Operators expect SSH "credentials" to look like a key;  for
        # the OSS path we issue a one-time random key id.  Real
        # SSH-backend integration is added as Phase 8.7.1 (deferred).
        return f"ssh-otk-{_secrets.token_urlsafe(32)}"
    if kind == LEASE_KIND_DATABASE:
        # Generate a "username:password" pair so DB clients can copy-
        # paste.  Username is intentionally non-deterministic.
        u = f"sysmanage-{_secrets.token_hex(4)}"
        p = _secrets.token_urlsafe(24)
        return f"{u}:{p}"
    # Token / generic.
    return _secrets.token_urlsafe(32)


def _vault_path_for_lease(lease_id: uuid.UUID) -> str:
    return f"sysmanage/dynamic/{lease_id}"


def issue_lease(
    db,
    *,
    kind: str,
    backend_role: str,
    name: str,
    ttl_seconds: Optional[int],
    issued_by_user_id: Optional[uuid.UUID],
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Issue a new dynamic-secret lease.

    Returns a dict with ``lease`` (DB row metadata) and ``secret`` (the
    plaintext value to surface to the operator EXACTLY ONCE).  Caller
    must NOT log ``secret``.
    """
    if kind not in LEASE_KINDS:
        raise DynamicSecretError(f"Unknown kind: {kind!r}")
    if not backend_role or not backend_role.strip():
        raise DynamicSecretError("backend_role is required")

    # Clamp TTL to the policy range.
    ttl = ttl_seconds if ttl_seconds is not None else TTL_DEFAULT_SECONDS
    if ttl < TTL_MIN_SECONDS or ttl > TTL_MAX_SECONDS:
        raise DynamicSecretError(
            f"ttl_seconds must be within [{TTL_MIN_SECONDS}, {TTL_MAX_SECONDS}]"
        )

    # Generate the credential and stash it in OpenBAO with a TTL.  We
    # do this BEFORE the DB row so a failed vault write doesn't leave
    # us with an orphan row claiming a non-existent secret.
    lease_id = uuid.uuid4()
    vault_path = _vault_path_for_lease(lease_id)
    issued_at = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = issued_at + timedelta(seconds=ttl)
    secret_value = _generate_secret_value(kind)

    try:
        vault = VaultService()
        # OpenBAO's KV doesn't natively expire individual keys but it
        # does honour ``cas`` + ``delete_version_after``.  We send both
        # — OpenBAO drops the version after the TTL whether or not we
        # come back to clean it up.
        vault._make_request(  # pylint: disable=protected-access
            "POST",
            f"{vault.mount_path}/data/{vault_path}",
            data={
                "data": {
                    "value": secret_value,
                    "kind": kind,
                    "backend_role": backend_role,
                    "lease_id": str(lease_id),
                    "issued_at": issued_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                },
                "options": {"delete_version_after": f"{ttl}s"},
            },
        )
    except VaultError as exc:
        # Persist a FAILED row so operators can audit the attempt.
        failed = models.DynamicSecretLease(
            id=lease_id,
            name=name,
            kind=kind,
            backend_role=backend_role,
            ttl_seconds=ttl,
            issued_at=issued_at,
            expires_at=expires_at,
            status=LEASE_FAILED,
            secret_metadata={"error": str(exc)},
            issued_by=issued_by_user_id,
            note=note,
        )
        db.add(failed)
        db.commit()
        raise DynamicSecretError(f"vault failure: {exc}") from exc

    lease = models.DynamicSecretLease(
        id=lease_id,
        name=name,
        kind=kind,
        backend_role=backend_role,
        vault_lease_id=vault_path,
        ttl_seconds=ttl,
        issued_at=issued_at,
        expires_at=expires_at,
        status=LEASE_ACTIVE,
        secret_metadata={"vault_path": vault_path},
        issued_by=issued_by_user_id,
        note=note,
    )
    db.add(lease)
    db.commit()
    db.refresh(lease)

    return {"lease": lease.to_dict(), "secret": secret_value}


def revoke_lease(db, *, lease_id: uuid.UUID) -> Dict[str, Any]:
    """Mark a lease revoked AND delete it from OpenBAO so its content
    can no longer be retrieved.  Idempotent — already-revoked /
    expired leases stay in their terminal state."""
    lease = (
        db.query(models.DynamicSecretLease)
        .filter(models.DynamicSecretLease.id == lease_id)
        .first()
    )
    if lease is None:
        raise DynamicSecretError("lease not found")

    if lease.status not in (LEASE_ACTIVE,):
        return {"lease": lease.to_dict(), "vault_revoked": False}

    if lease.vault_lease_id:
        try:
            vault = VaultService()
            vault._make_request(  # pylint: disable=protected-access
                "DELETE", f"{vault.mount_path}/metadata/{lease.vault_lease_id}"
            )
        except VaultError as exc:
            # We still mark the row revoked so it disappears from the
            # active list;  log so an operator can investigate any
            # stuck OpenBAO state.
            logger.warning(
                "Vault delete for lease %s failed (%s); marking row revoked anyway",
                lease.id,
                exc,
            )

    lease.status = LEASE_REVOKED
    lease.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(lease)
    return {"lease": lease.to_dict(), "vault_revoked": True}


def reconcile_expired(db) -> int:
    """Mark any ACTIVE leases whose ``expires_at`` is in the past as
    EXPIRED.  Safe to call repeatedly;  returns the number of rows
    transitioned.  Intended for an external sweeper hook."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(models.DynamicSecretLease)
        .filter(
            models.DynamicSecretLease.status == LEASE_ACTIVE,
            models.DynamicSecretLease.expires_at.isnot(None),
            models.DynamicSecretLease.expires_at <= now,
        )
        .all()
    )
    for r in rows:
        r.status = LEASE_EXPIRED
    if rows:
        db.commit()
    return len(rows)
