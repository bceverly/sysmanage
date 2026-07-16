# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
API-key authentication helpers — Phase 13.2 (API Completeness).

Generation, hashing, and verification for the ``ApiKey`` model.  An API key is
an alternative bearer credential for automation: presented in the same
``Authorization: Bearer <key>`` header as a JWT, but distinguished by the
``smk_`` prefix ("sysmanage key").  ``auth_bearer`` falls back to this module
when a presented bearer credential is not a valid JWT, so every endpoint that
already accepts a JWT transparently accepts an API key — no per-endpoint change.

Storage is GitHub-PAT style: only ``sha256(key)`` is persisted, so the secret
is unrecoverable from the database.  Verification hashes the presented key and
does a single indexed lookup.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Distinguishes an API key from a JWT in the shared Bearer header.  JWTs are
# three base64url segments joined by '.', so this prefix can never collide.
API_KEY_PREFIX = "smk_"
# Length (chars) of the non-secret display slice kept in ``key_prefix``.
_PREFIX_DISPLAY_LEN = 12


def generate_api_key() -> Tuple[str, str, str]:
    """Mint a new API key.

    Returns ``(full_key, key_hash, key_prefix)``:
      * ``full_key`` — the plaintext, shown to the user exactly once.
      * ``key_hash`` — SHA-256 hex digest to persist.
      * ``key_prefix`` — non-secret leading slice for display/audit.
    """
    full_key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return full_key, hash_api_key(full_key), full_key[:_PREFIX_DISPLAY_LEN]


def hash_api_key(full_key: str) -> str:
    """Return the SHA-256 hex digest used for storage and lookup.

    SHA-256 (a fast hash) is the CORRECT choice here, NOT a slow KDF like
    Argon2/bcrypt: an API key is a 256-bit cryptographically-random token
    (``secrets.token_urlsafe(32)``), so it has full machine entropy and is not
    brute-forceable from its digest — the threat a slow KDF defends against
    (low-entropy human passwords) does not apply.  A fast digest also enables the
    O(1) indexed lookup in ``authenticate_api_key`` (a per-record salted KDF
    cannot be indexed).  This is the same model GitHub uses for personal access
    tokens.  CodeQL's ``py/weak-sensitive-data-hashing`` flags this generically
    (it can't see the input's entropy) — it is a false positive in this context.
    """
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def looks_like_api_key(credential: Optional[str]) -> bool:
    """True when a bearer credential is shaped like an API key (not a JWT)."""
    return bool(credential) and credential.startswith(API_KEY_PREFIX)


def authenticate_api_key(credential: str) -> Optional[dict]:
    """Validate an API key and return its principal, or ``None``.

    On success returns ``{"user_id": <userid>, "tenant_id": <str|None>}`` —
    ``user_id`` is the owning user's login id (the same value a JWT carries in
    its ``user_id`` claim), so downstream resolution (``get_current_user`` →
    ``require_authenticated_user``) is identical for both auth types.  Also
    stamps ``last_used_at`` best-effort.  Returns ``None`` for any unusable key:
    unknown, revoked, expired, or owned by a missing/locked/inactive user.
    """
    if not looks_like_api_key(credential):
        return None

    # Late imports keep this module importable without eagerly pulling in the
    # DB/engine stack (mirrors auth_bearer.require_authenticated_user).
    from sqlalchemy.orm import sessionmaker  # noqa: PLC0415

    from backend.persistence import db as db_module  # noqa: PLC0415
    from backend.persistence.models import ApiKey, User  # noqa: PLC0415

    key_hash = hash_api_key(credential)
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )
    session = session_local()
    try:
        key = session.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if key is None or not key.is_usable():
            return None
        user = session.query(User).filter(User.id == key.user_id).first()
        if user is None or user.active is False or user.is_locked:
            return None
        principal = {
            "user_id": user.userid,
            "tenant_id": str(key.tenant_id) if key.tenant_id else None,
        }
        # Best-effort usage stamp; never let a write failure block auth.
        try:
            key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - usage tracking is non-critical
            session.rollback()
            # Logs the caught exception object, not the API key/credential.
            # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
            logger.debug("api-key last_used_at update failed: %s", exc)
        return principal
    finally:
        session.close()
