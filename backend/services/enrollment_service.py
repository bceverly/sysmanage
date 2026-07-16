# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tenant enrollment tokens — OSS shim (Pro+ relocation, Phase 2).

An admin generates a tenant-scoped enrollment token; an agent presents it at
registration to enrol into that tenant.  The token logic (generation, hashing,
listing, revocation, validation/consumption) moved into the licensed
``multitenancy_engine`` — the OSS build has no copy — so these are thin
delegators (session-in, passed straight through to the engine).

The control-plane CRUD operations (generate/list/revoke) require the engine and
raise a clear error without it (they're only reachable when multi-tenancy is
enabled).  The registration read path (:func:`validate_and_consume`) degrades to
``None`` — a single-tenant / unlicensed server has no enrollment tokens.
"""

from typing import List, Optional

from backend.multitenancy import seam


def _engine_or_raise():
    engine = seam.engine_module()
    if engine is None:
        raise RuntimeError(
            "Enrollment tokens require the licensed multi-tenancy engine, which "
            "is not loaded. Multi-tenancy is a Pro+ MULTITENANT_SAAS capability."
        )
    return engine


def generate_token(
    session,
    tenant_id: str,
    *,
    label: Optional[str] = None,
    expires_at=None,
    max_uses: Optional[int] = None,
    created_by: Optional[str] = None,
):
    """Create a token for ``tenant_id``; return (plaintext, row)."""
    return _engine_or_raise().generate_token(
        session,
        tenant_id,
        label=label,
        expires_at=expires_at,
        max_uses=max_uses,
        created_by=created_by,
    )


def list_tokens(session, tenant_id: str) -> List:
    """Return a tenant's enrollment tokens (newest first); never the plaintext."""
    return _engine_or_raise().list_tokens(session, tenant_id)


def revoke_token(session, tenant_id: str, token_id: str) -> bool:
    """Revoke a token (disables it immediately).  Returns True if found."""
    return _engine_or_raise().revoke_token(session, tenant_id, token_id)


def validate_and_consume(session, plaintext: str) -> Optional[str]:
    """Resolve a plaintext token to its tenant_id, consuming one use.

    Returns None when multi-tenancy isn't active (no tokens exist) or the token
    is unknown/invalid; the engine handles the valid case.
    """
    engine = seam.engine_module()
    if engine is None:
        return None
    return engine.validate_and_consume(session, plaintext)
