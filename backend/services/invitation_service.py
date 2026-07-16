# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Administrator-invitation service (Phase 13.3).

An admin invites a person by email with a set of security roles.  The recipient
accepts via a one-time tokened link, which creates their ``User`` account,
assigns the roles, sets their chosen password, and marks the invitation
accepted.  Mirrors the password-reset token pattern but creates the account on
accept (it does not exist beforehand).

Pure data-layer helpers — the caller owns the session and commits.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from argon2 import PasswordHasher

from backend.persistence import models

# Invitations live longer than a password reset (24h) — a new hire may take a
# few days to accept.
INVITATION_TTL_DAYS = 7

_argon2 = PasswordHasher()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InvitationError(Exception):
    """Raised for invalid invitation operations (caller maps to HTTP)."""


def create_invitation(
    session,
    *,
    email: str,
    invited_by: Optional[str],
    role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> models.UserInvitation:
    """Create a pending invitation for ``email``.

    Rejects if a user with that email already exists.  Supersedes (revokes) any
    still-pending invitation for the same email so there is at most one live
    token per address.  Validates that every role id exists.
    """
    existing_user = (
        session.query(models.User).filter(models.User.userid == email).first()
    )
    if existing_user is not None:
        raise InvitationError("A user with that email already exists")

    role_ids = role_ids or []
    if role_ids:
        found = (
            session.query(models.SecurityRole.id)
            .filter(models.SecurityRole.id.in_(role_ids))
            .count()
        )
        if found != len(set(role_ids)):
            raise InvitationError("One or more security roles do not exist")

    # Supersede any live invitation for the same email.
    for inv in (
        session.query(models.UserInvitation)
        .filter(models.UserInvitation.email == email)
        .all()
    ):
        if inv.is_pending():
            inv.revoked_at = _now()

    invitation = models.UserInvitation(
        email=email,
        token=str(uuid.uuid4()),
        invited_by=invited_by,
        is_admin=bool(is_admin),
        role_ids=list(role_ids),
        first_name=first_name,
        last_name=last_name,
        created_at=_now(),
        expires_at=_now() + timedelta(days=INVITATION_TTL_DAYS),
    )
    session.add(invitation)
    session.flush()
    return invitation


def list_invitations(
    session, *, pending_only: bool = False
) -> List[models.UserInvitation]:
    """Return invitations, newest first; optionally only the still-pending ones."""
    rows = (
        session.query(models.UserInvitation)
        .order_by(models.UserInvitation.created_at.desc())
        .all()
    )
    if pending_only:
        rows = [r for r in rows if r.is_pending()]
    return rows


def get_invitation(session, invitation_id) -> Optional[models.UserInvitation]:
    return (
        session.query(models.UserInvitation)
        .filter(models.UserInvitation.id == invitation_id)
        .first()
    )


def revoke_invitation(session, invitation_id) -> bool:
    """Revoke a pending invitation. Returns True if it was pending and revoked."""
    inv = get_invitation(session, invitation_id)
    if inv is None or not inv.is_pending():
        return False
    inv.revoked_at = _now()
    return True


def get_valid_invitation(session, token: str) -> Optional[models.UserInvitation]:
    """Return the invitation for ``token`` iff it is still pending, else None."""
    inv = (
        session.query(models.UserInvitation)
        .filter(models.UserInvitation.token == token)
        .first()
    )
    if inv is not None and inv.is_pending():
        return inv
    return None


def accept_invitation(
    session,
    *,
    token: str,
    password: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> models.User:
    """Accept an invitation: create the user, assign roles, set the password.

    Raises ``InvitationError`` for an invalid/expired token or if the email was
    claimed by another account since the invite was sent.
    """
    inv = get_valid_invitation(session, token)
    if inv is None:
        raise InvitationError("Invalid or expired invitation")

    if (
        session.query(models.User).filter(models.User.userid == inv.email).first()
        is not None
    ):
        # Email got an account between invite and accept — don't double-create.
        inv.revoked_at = _now()
        raise InvitationError("A user with that email already exists")

    user = models.User(
        userid=inv.email,
        hashed_password=_argon2.hash(password),
        active=True,
        is_admin=bool(inv.is_admin),
        first_name=first_name if first_name is not None else inv.first_name,
        last_name=last_name if last_name is not None else inv.last_name,
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(user)
    session.flush()  # populate user.id for the role links

    for role_id in inv.role_ids or []:
        session.add(
            models.UserSecurityRole(user_id=user.id, role_id=role_id, granted_at=_now())
        )

    inv.accepted_at = _now()
    return user
