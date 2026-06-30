"""Administrator-invitation API (Phase 13.3).

Admins invite people by email with a set of security roles; the recipient
accepts via a one-time tokened link that creates their account, assigns the
roles, and sets their password.

Routes (mounted by ``_include_versioned`` at ``/api/v1/invitations`` + a
deprecated ``/api`` alias):

* admin (JWT + ``ADD_USER``): ``POST /``, ``GET /``, ``DELETE /{id}``,
  ``POST /{id}/resend``
* public (tokened): ``GET /validate/{token}``, ``POST /accept``
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import error_user_not_found
from backend.api.password_reset import get_dynamic_hostname
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services import invitation_service
from backend.services.email_service import email_service
from backend.services.tenant_directory import resolve_tenant_for_email

router = APIRouter(prefix="/invitations", tags=["invitations"])

_MIN_PASSWORD_LEN = 8


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class CreateInvitationRequest(BaseModel):
    """Admin request to invite a new user."""

    email: EmailStr
    role_ids: List[str] = []
    is_admin: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class AcceptInvitationRequest(BaseModel):
    """Recipient request to accept an invitation and set a password."""

    token: str
    password: str
    confirm_password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class InvitationResponse(BaseModel):
    """An invitation as returned to admins."""

    id: str
    email: str
    is_admin: bool
    role_ids: List[str]
    first_name: Optional[str]
    last_name: Optional[str]
    invited_by: Optional[str]
    created_at: Optional[str]
    expires_at: Optional[str]
    status: str  # pending | accepted | revoked | expired


class SimpleResponse(BaseModel):
    success: bool
    message: str


def _status(inv: models.UserInvitation) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if inv.revoked_at is not None:
        return "revoked"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if inv.expires_at is not None and inv.expires_at <= now:
        return "expired"
    return "pending"


def _to_response(inv: models.UserInvitation) -> InvitationResponse:
    return InvitationResponse(
        id=str(inv.id),
        email=inv.email,
        is_admin=bool(inv.is_admin),
        role_ids=list(inv.role_ids or []),
        first_name=inv.first_name,
        last_name=inv.last_name,
        invited_by=inv.invited_by,
        created_at=inv.created_at.isoformat() if inv.created_at else None,
        expires_at=inv.expires_at.isoformat() if inv.expires_at else None,
        status=_status(inv),
    )


def _require_add_user(session, current_user: str):
    """Resolve the caller and enforce the ADD_USER role, else 401/403."""
    auth_user = (
        session.query(models.User).filter(models.User.userid == current_user).first()
    )
    if not auth_user:
        raise HTTPException(status_code=401, detail=error_user_not_found())
    if auth_user._role_cache is None:  # noqa: SLF001 - established pattern
        auth_user.load_role_cache(session)
    if not auth_user.has_role(SecurityRoles.ADD_USER):
        raise HTTPException(
            status_code=403,
            detail=_("Permission denied: Add User role required"),
        )
    return auth_user


def send_invitation_email(email: str, token: str, _request: Request) -> bool:
    """Send the invitation email with a one-time accept link."""
    if not email_service.is_enabled():
        return False

    the_config = config.get_config()
    is_secure = bool(the_config.get("api", {}).get("certFile"))
    protocol = "https" if is_secure else "http"
    hostname = get_dynamic_hostname()
    frontend_port = the_config.get("webui", {}).get("port", 3000)
    accept_url = (
        f"{protocol}://{hostname}:{frontend_port}/accept-invitation?token={token}"
    )

    templates = the_config.get("email", {}).get("templates", {})
    tmpl = templates.get("invitation", {})
    subject = tmpl.get("subject", "You've been invited to SysManage")
    body = tmpl.get(
        "text_body",
        """Hello,

You have been invited to SysManage by an administrator.

To accept the invitation and set your password, click the link below:
{accept_url}

This invitation will expire in 7 days.

If you did not expect this email, you can ignore it.

--
SysManage System""",
    ).format(accept_url=accept_url)
    html_body = tmpl.get(
        "html_body",
        """<html><body>
<p>Hello,</p>
<p>You have been invited to SysManage by an administrator.</p>
<p>To accept the invitation and set your password, click the link below:</p>
<p><a href="{accept_url}">Accept Invitation</a></p>
<p>This invitation will expire in 7 days.</p>
<p>If you did not expect this email, you can ignore it.</p>
<hr><p><em>SysManage System</em></p>
</body></html>""",
    ).format(accept_url=accept_url)

    return email_service.send_email(
        to_addresses=[email],
        subject=subject,
        body=body,
        html_body=html_body,
        tenant_id=resolve_tenant_for_email(email),
    )


def _sessionmaker():
    return sessionmaker(autocommit=False, autoflush=False, bind=db.get_engine())


# --------------------------------------------------------------------------- #
# Admin routes
# --------------------------------------------------------------------------- #
@router.post("", dependencies=[Depends(JWTBearer())])
async def create_invitation(
    body: CreateInvitationRequest,
    request: Request,
    current_user: str = Depends(get_current_user),
) -> InvitationResponse:
    """Create an invitation and email the recipient a one-time accept link."""
    with _sessionmaker()() as session:
        _require_add_user(session, current_user)
        try:
            inv = invitation_service.create_invitation(
                session,
                email=str(body.email),
                invited_by=current_user,
                role_ids=body.role_ids,
                is_admin=body.is_admin,
                first_name=body.first_name,
                last_name=body.last_name,
            )
        except invitation_service.InvitationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        token = inv.token
        session.commit()
        session.refresh(inv)
        resp = _to_response(inv)

    send_invitation_email(resp.email, token, request)
    return resp


@router.get("", dependencies=[Depends(JWTBearer())])
async def list_invitations(
    pending_only: bool = False,
    current_user: str = Depends(get_current_user),
) -> List[InvitationResponse]:
    """List invitations (newest first); ``pending_only`` filters to live ones."""
    with _sessionmaker()() as session:
        _require_add_user(session, current_user)
        rows = invitation_service.list_invitations(session, pending_only=pending_only)
        return [_to_response(r) for r in rows]


@router.delete("/{invitation_id}", dependencies=[Depends(JWTBearer())])
async def revoke_invitation(
    invitation_id: str,
    current_user: str = Depends(get_current_user),
) -> SimpleResponse:
    """Revoke a pending invitation."""
    with _sessionmaker()() as session:
        _require_add_user(session, current_user)
        if not invitation_service.revoke_invitation(session, invitation_id):
            raise HTTPException(
                status_code=404, detail=_("No pending invitation found")
            )
        session.commit()
    return SimpleResponse(success=True, message=_("Invitation revoked"))


@router.post("/{invitation_id}/resend", dependencies=[Depends(JWTBearer())])
async def resend_invitation(
    invitation_id: str,
    request: Request,
    current_user: str = Depends(get_current_user),
) -> SimpleResponse:
    """Re-send the email for a still-pending invitation."""
    with _sessionmaker()() as session:
        _require_add_user(session, current_user)
        inv = invitation_service.get_invitation(session, invitation_id)
        if inv is None or not inv.is_pending():
            raise HTTPException(
                status_code=404, detail=_("No pending invitation found")
            )
        email, token = inv.email, inv.token

    sent = send_invitation_email(email, token, request)
    if not sent:
        raise HTTPException(
            status_code=500,
            detail=_(
                "Failed to send invitation email. Please check email configuration."
            ),
        )
    return SimpleResponse(
        success=True, message=_("Invitation re-sent to {email}").format(email=email)
    )


# --------------------------------------------------------------------------- #
# Public (tokened) routes
# --------------------------------------------------------------------------- #
@router.get("/validate/{token}")
async def validate_invitation(token: str) -> InvitationResponse:
    """Validate an invitation token (used by the accept page on load)."""
    with _sessionmaker()() as session:
        inv = invitation_service.get_valid_invitation(session, token)
        if inv is None:
            raise HTTPException(
                status_code=400, detail=_("Invalid or expired invitation")
            )
        return _to_response(inv)


@router.post("/accept")
async def accept_invitation(body: AcceptInvitationRequest) -> SimpleResponse:
    """Accept an invitation: create the account, assign roles, set the password."""
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail=_("Passwords do not match"))
    if len(body.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=_("Password must be at least 8 characters long"),
        )
    with _sessionmaker()() as session:
        try:
            invitation_service.accept_invitation(
                session,
                token=body.token,
                password=body.password,
                first_name=body.first_name,
                last_name=body.last_name,
            )
        except invitation_service.InvitationError as exc:
            session.commit()  # persist a revoke side-effect if any
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
    return SimpleResponse(
        success=True,
        message=_("Your account is ready. You can now log in."),
    )
