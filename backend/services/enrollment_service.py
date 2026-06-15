"""
Tenant enrollment tokens — Phase 13.1 (data plane).

An admin generates a tenant-scoped enrollment token; an agent presents it at
registration to be enrolled into that tenant.  Only the SHA-256 hash is stored;
the plaintext is returned once at creation and never persisted.

This is the *service* layer (pure-ish, session-in): generation, listing,
revocation, and validation.  The control-plane API wraps create/list/revoke;
the registration path (Phase 13.1 slice 2) calls :func:`validate_and_consume`.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from backend.persistence.models.tenancy import RegistryEnrollmentToken

# Plaintext tokens are prefixed so they're recognizable in logs/configs and so
# we can evolve the format later.  The prefix is part of the hashed material.
_TOKEN_PREFIX = "sme_"  # nosec B105 - token format prefix, not a secret


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(plaintext: str) -> str:
    """SHA-256 hex of a plaintext token (the stored/looked-up form)."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_token(
    session,
    tenant_id: str,
    *,
    label: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    max_uses: Optional[int] = None,
    created_by: Optional[str] = None,
) -> tuple[str, RegistryEnrollmentToken]:
    """Create a token for ``tenant_id``; return (plaintext, row).

    The plaintext is shown to the operator ONCE — only its hash is stored.
    """
    plaintext = _TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = RegistryEnrollmentToken(
        tenant_id=tenant_id,
        token_hash=hash_token(plaintext),
        label=label,
        expires_at=expires_at,
        max_uses=max_uses,
        use_count=0,
        revoked=False,
        created_by=created_by,
        created_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return plaintext, row


def list_tokens(session, tenant_id: str) -> List[RegistryEnrollmentToken]:
    """Return a tenant's enrollment tokens (newest first); never the plaintext."""
    return (
        session.query(RegistryEnrollmentToken)
        .filter(RegistryEnrollmentToken.tenant_id == tenant_id)
        .order_by(RegistryEnrollmentToken.created_at.desc())
        .all()
    )


def revoke_token(session, tenant_id: str, token_id: str) -> bool:
    """Revoke a token (disables it immediately).  Returns True if found."""
    row = (
        session.query(RegistryEnrollmentToken)
        .filter(
            RegistryEnrollmentToken.id == token_id,
            RegistryEnrollmentToken.tenant_id == tenant_id,
        )
        .first()
    )
    if row is None:
        return False
    row.revoked = True
    session.commit()
    return True


def _is_usable(row: RegistryEnrollmentToken, now: datetime) -> bool:
    if row.revoked:
        return False
    if row.expires_at is not None and row.expires_at <= now:
        return False
    if row.max_uses is not None and (row.use_count or 0) >= row.max_uses:
        return False
    return True


def validate_and_consume(session, plaintext: str) -> Optional[str]:
    """Resolve a plaintext token to its tenant_id, consuming one use.

    Returns the ``tenant_id`` (str) when the token is valid (not revoked, not
    expired, uses remaining), bumping ``use_count`` / ``last_used_at``.  Returns
    ``None`` for an unknown/invalid token.  Used by the agent registration path.
    """
    if not plaintext:
        return None
    now = _utcnow()
    row = (
        session.query(RegistryEnrollmentToken)
        .filter(RegistryEnrollmentToken.token_hash == hash_token(plaintext))
        .first()
    )
    if row is None or not _is_usable(row, now):
        return None
    row.use_count = (row.use_count or 0) + 1
    row.last_used_at = now
    session.commit()
    return str(row.tenant_id)
