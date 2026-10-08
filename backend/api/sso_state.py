# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""SSO sign-ins in progress, shared by every server worker (Phase 22.8).

``/start`` records the OIDC ``state`` (or SAML ``RelayState``) here and the
IdP's return claims it.  It used to be a dict in one worker's memory, which
fails whenever the return reaches another worker -- with several workers,
often.  A claim deletes the row, so a state is good for one sign-in, and a
row older than ``MAX_AGE_SECONDS`` is refused (and swept on the next start).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.persistence import models

# Long enough to sign in with MFA (a push, a code, a security key), short
# enough that an abandoned start is soon worthless.
MAX_AGE_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def save(db: Session, state: str, provider_id, request_id: Optional[str] = None):
    """Record a sign-in that has just been sent to the IdP."""
    cutoff = _now() - timedelta(seconds=MAX_AGE_SECONDS)
    db.query(models.SsoPendingState).filter(
        models.SsoPendingState.created_at < cutoff
    ).delete(synchronize_session=False)
    db.add(
        models.SsoPendingState(
            state=state,
            provider_id=provider_id,
            request_id=request_id,
            created_at=_now(),
        )
    )
    db.commit()


def claim(db: Session, state: str) -> Optional[Tuple[str, Optional[str]]]:
    """``(provider_id, request_id)`` for a state still waiting, removing it so
    it cannot be used twice; None when unknown, used or expired."""
    row = db.get(models.SsoPendingState, state)
    if row is None:
        return None
    provider_id, request_id, created_at = (
        str(row.provider_id),
        row.request_id,
        row.created_at,
    )
    deleted = (
        db.query(models.SsoPendingState)
        .filter(models.SsoPendingState.state == state)
        .delete(synchronize_session=False)
    )
    db.commit()
    if not deleted:
        return None  # another worker claimed it first
    if created_at < _now() - timedelta(seconds=MAX_AGE_SECONDS):
        return None
    return provider_id, request_id
