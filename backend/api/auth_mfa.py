"""
Multi-Factor Authentication endpoints (Phase 10.3).

Routes:

  POST /api/auth/mfa/enroll/start
      Authenticated.  Generate a fresh TOTP secret for the current
      user and return the provisioning URI + base32 secret + QR-friendly
      otpauth URL.  The secret is stored encrypted; final enrollment
      isn't recorded until ``enroll/complete`` succeeds.

  POST /api/auth/mfa/enroll/complete
      Authenticated.  Verify the user's first TOTP code, then issue
      backup codes.  Returns the plaintext backup codes exactly once —
      they are never retrievable again.

  POST /api/auth/mfa/verify
      Anonymous (uses an MFA-pending token from the login response).
      Exchanges the pending token + a TOTP / backup code for a real
      session JWT.

  POST /api/auth/mfa/disable
      Authenticated.  Requires the user's current password to remove
      the enrollment row.

  GET /api/auth/mfa/status
      Authenticated.  Returns the current user's enrollment shape
      (enrolled_at / last_used_at / remaining backup codes / whether
      admin-required-policy applies to them).

  POST /api/auth/mfa/backup-codes/regenerate
      Authenticated.  Requires a fresh TOTP code to invalidate the
      old backup codes and return a new set.

  GET /api/settings/mfa
      Authenticated (admin).  Return the singleton MfaSettings row.

  PUT /api/settings/mfa
      Authenticated (admin).  Update issuer / digits / period /
      backup-code-count / admin_required / grace_period_days.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.auth.auth_handler import (
    decode_mfa_pending_token,
    sign_jwt,
)
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services import mfa_service
from backend.services.audit_service import (
    ActionType,
    AuditService,
    EntityType,
    Result,
)

logger = logging.getLogger(__name__)
argon2_hasher = PasswordHasher()

router = APIRouter()


# ---------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------


class EnrollStartResponse(BaseModel):
    """Response from ``enroll/start`` — URI for the authenticator app +
    the raw secret for users who can't scan the QR."""

    secret: str
    provisioning_uri: str
    issuer: str
    account_name: str


class EnrollCompleteRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=10)


class EnrollCompleteResponse(BaseModel):
    backup_codes: List[str]
    enrolled_at: str


class VerifyRequest(BaseModel):
    pending_token: str
    code: str = Field(..., min_length=4, max_length=20)


class EmailRequestRequest(BaseModel):
    """Request body for /api/auth/mfa/email/request.

    Re-uses the same MFA-pending token the verify endpoint accepts —
    the user has already passed the password step but not yet the
    second factor.  No other fields: ``user_id`` and ``email`` are
    decoded from the token + looked up in the DB to avoid an open
    "send me a code to <arbitrary email>" vector.
    """

    pending_token: str


class DisableRequest(BaseModel):
    password: str


class RegenerateRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=10)


class StatusResponse(BaseModel):
    enrolled: bool
    enrolled_at: Optional[str] = None
    last_used_at: Optional[str] = None
    last_used_method: Optional[str] = None
    remaining_backup_codes: int = 0
    admin_required: bool = False
    grace_period_days: int = 14


class MfaSettingsRequest(BaseModel):
    issuer_name: Optional[str] = Field(None, min_length=1, max_length=120)
    totp_digits: Optional[int] = Field(None, ge=6, le=8)
    totp_period_seconds: Optional[int] = Field(None, ge=15, le=120)
    backup_code_count: Optional[int] = Field(None, ge=0, le=20)
    admin_required: Optional[bool] = None
    grace_period_days: Optional[int] = Field(None, ge=0, le=365)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _get_user_or_404(db: Session, userid: str) -> models.User:
    user = db.query(models.User).filter(models.User.userid == userid).first()
    if not user:
        raise HTTPException(status_code=404, detail=_("User not found"))
    return user


def _audit(
    db: Session,
    user: Optional[models.User],
    description: str,
    success: bool,
    details: Optional[dict] = None,
) -> None:
    AuditService.log(
        db=db,
        user_id=user.id if user else None,
        username=user.userid if user else None,
        action_type=ActionType.LOGIN,
        entity_type=EntityType.USER,
        entity_id=str(user.id) if user else None,
        entity_name=user.userid if user else None,
        description=description,
        result=Result.SUCCESS if success else Result.FAILURE,
        details=details or {},
    )


# ---------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------


@router.post(
    "/api/auth/mfa/enroll/start",
    response_model=EnrollStartResponse,
    dependencies=[Depends(JWTBearer())],
)
async def enroll_start(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Generate a fresh TOTP secret and return its provisioning URI.

    Calling this when an enrollment already exists OVERWRITES the
    secret in the user's row but leaves it in a "pending" state until
    ``enroll/complete`` succeeds.  Backup codes are not generated yet.
    """
    user = _get_user_or_404(db, current_user)
    settings = mfa_service.get_settings(db)
    secret = mfa_service.generate_totp_secret()
    encrypted = mfa_service.encrypt_secret(secret)

    enrollment = mfa_service.get_enrollment(db, user.id)
    if enrollment is None:
        enrollment = models.UserMfaEnrollment(
            user_id=user.id,
            totp_secret_encrypted=encrypted,
            backup_codes_hashed=[],
            enrolled_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(enrollment)
    else:
        # Re-enroll: blow away old secret + codes; user will need to
        # re-scan and re-save backup codes.
        enrollment.totp_secret_encrypted = encrypted
        enrollment.backup_codes_hashed = []
        enrollment.last_used_at = None
        enrollment.last_used_method = None
    db.commit()

    uri = mfa_service.provisioning_uri(secret, user.userid, settings)
    _audit(db, user, "MFA enrollment started", success=True)
    return EnrollStartResponse(
        secret=secret,
        provisioning_uri=uri,
        issuer=settings.issuer_name,
        account_name=user.userid,
    )


@router.post(
    "/api/auth/mfa/enroll/complete",
    response_model=EnrollCompleteResponse,
    dependencies=[Depends(JWTBearer())],
)
async def enroll_complete(
    request: EnrollCompleteRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Verify the first TOTP code, then issue backup codes.

    Returns the plaintext backup codes ONCE — store-and-forget design.
    """
    user = _get_user_or_404(db, current_user)
    enrollment = mfa_service.get_enrollment(db, user.id)
    if enrollment is None or not enrollment.totp_secret_encrypted:
        raise HTTPException(
            status_code=400,
            detail=_("Call enroll/start before enroll/complete."),
        )
    settings = mfa_service.get_settings(db)
    secret = mfa_service.decrypt_secret(enrollment.totp_secret_encrypted)
    if not mfa_service.verify_totp(secret, request.code, settings):
        _audit(
            db,
            user,
            "MFA enrollment verify failed",
            success=False,
            details={"reason": "invalid_totp_code"},
        )
        raise HTTPException(status_code=400, detail=_("Invalid TOTP code."))

    plaintext_backup = mfa_service.generate_backup_codes(settings.backup_code_count)
    enrollment.backup_codes_hashed = mfa_service.hash_backup_codes(plaintext_backup)
    enrollment.enrolled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    _audit(
        db,
        user,
        "MFA enrollment completed",
        success=True,
        details={"backup_code_count": len(plaintext_backup)},
    )
    return EnrollCompleteResponse(
        backup_codes=plaintext_backup,
        enrolled_at=enrollment.enrolled_at.isoformat(),
    )


# ---------------------------------------------------------------------
# Login challenge — anonymous endpoint, validates MFA-pending token
# ---------------------------------------------------------------------


@router.post("/api/auth/mfa/verify")
async def mfa_verify(
    request: VerifyRequest,
    db: Session = Depends(get_db),
):
    """Exchange an MFA-pending token + TOTP / backup code for a real
    session JWT.  Called by the login UI after ``/api/login`` returned
    ``{mfa_required: true, pending_token: "..."}`` instead of a session.
    """
    pending = decode_mfa_pending_token(request.pending_token)
    if not pending:
        raise HTTPException(
            status_code=401,
            detail=_("MFA challenge expired — please log in again."),
        )
    userid = pending.get("user_id")
    user = db.query(models.User).filter(models.User.userid == userid).first()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail=_("Invalid MFA challenge."))

    ok, method = mfa_service.verify_user_code(db, user.id, request.code)
    if not ok:
        _audit(
            db,
            user,
            "MFA verify failed",
            success=False,
            details={"reason": "invalid_code"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail=_("Invalid MFA code."))

    db.commit()
    _audit(
        db,
        user,
        f"MFA verify success ({method})",
        success=True,
        details={"method": method},
    )
    return {"Authorization": sign_jwt(user.userid), "method": method}


@router.post("/api/auth/mfa/email/request")
async def mfa_email_request(
    request: EmailRequestRequest,
    fastapi_request: Request,
    db: Session = Depends(get_db),
):
    """Issue an email-OTP code to the user's registered email address.

    Phase 10.3 fallback for users who can't reach their authenticator
    app and have no backup codes left.  Requires the same pending
    token the verify endpoint accepts — the user must have already
    passed the password step (so we know which user to send to and
    that the request isn't a random spammer).

    Always returns 200 with a generic envelope, *regardless of whether
    the user is enrolled in MFA or whether the email send succeeded*.
    Surfacing those signals would let an attacker probe which userids
    have MFA enabled or whether a given email is registered.  Real
    failures land in the audit log + server logs only.
    """
    pending = decode_mfa_pending_token(request.pending_token)
    if not pending:
        raise HTTPException(
            status_code=401,
            detail=_("MFA challenge expired — please log in again."),
        )
    userid = pending.get("user_id")
    user = db.query(models.User).filter(models.User.userid == userid).first()

    # Single exit point with the always-identical envelope.  Every
    # branch below produces side effects (audit log + maybe OTP send)
    # but the wire-level response NEVER differentiates — that's the
    # anti-enumeration property described in the docstring.  Bad
    # pending token resolves to a missing/inactive user → same as the
    # not-enrolled case; probing the endpoint gives an attacker no
    # information about which userids exist or are MFA-enrolled.
    if user and user.active:
        if mfa_service.is_enrolled(db, user.id):
            # Source IP is best-effort — behind a reverse proxy the
            # request will carry X-Forwarded-For; we trust whatever
            # ``fastapi_request.client`` surfaces and log only.  Not
            # used for any auth decision.
            client = getattr(fastapi_request, "client", None)
            source_ip = client.host if client is not None else None
            sent = mfa_service.request_email_otp(
                db,
                user_id=user.id,
                user_email=user.userid,
                ip_address=source_ip,
            )
            _audit(
                db,
                user,
                "MFA email-OTP requested",
                success=True,
                details={"sent": sent},
            )
        else:
            _audit(
                db,
                user,
                "MFA email-OTP request ignored (not enrolled)",
                success=True,
                details={"reason": "not_enrolled"},
            )
        db.commit()

    return {
        "sent": True,
        "message": _(
            "If your account has MFA configured, an email with a "
            "verification code has been dispatched."
        ),
    }


# ---------------------------------------------------------------------
# Disable / status / regenerate
# ---------------------------------------------------------------------


@router.post("/api/auth/mfa/disable", dependencies=[Depends(JWTBearer())])
async def mfa_disable(
    request: DisableRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Disable MFA for the current user.  Requires the user's password
    so a stolen session token can't silently turn the second factor off.
    """
    user = _get_user_or_404(db, current_user)
    try:
        argon2_hasher.verify(user.hashed_password, request.password)
    except VerifyMismatchError as exc:
        _audit(
            db,
            user,
            "MFA disable rejected (bad password)",
            success=False,
        )
        raise HTTPException(status_code=401, detail=_("Invalid password.")) from exc
    enrollment = mfa_service.get_enrollment(db, user.id)
    if enrollment is not None:
        db.delete(enrollment)
        db.commit()
    _audit(db, user, "MFA disabled", success=True)
    return {"message": _("MFA disabled."), "enrolled": False}


@router.get(
    "/api/auth/mfa/status",
    response_model=StatusResponse,
    dependencies=[Depends(JWTBearer())],
)
async def mfa_status(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Return the current user's MFA enrollment summary."""
    user = _get_user_or_404(db, current_user)
    enrollment = mfa_service.get_enrollment(db, user.id)
    settings = mfa_service.get_settings(db)
    if enrollment is None:
        return StatusResponse(
            enrolled=False,
            admin_required=settings.admin_required,
            grace_period_days=settings.grace_period_days,
        )
    return StatusResponse(
        enrolled=True,
        enrolled_at=(
            enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None
        ),
        last_used_at=(
            enrollment.last_used_at.isoformat() if enrollment.last_used_at else None
        ),
        last_used_method=enrollment.last_used_method,
        remaining_backup_codes=enrollment.remaining_backup_codes(),
        admin_required=settings.admin_required,
        grace_period_days=settings.grace_period_days,
    )


@router.post(
    "/api/auth/mfa/backup-codes/regenerate",
    response_model=EnrollCompleteResponse,
    dependencies=[Depends(JWTBearer())],
)
async def regenerate_backup_codes(
    request: RegenerateRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Issue a fresh set of backup codes (invalidates the old set).
    Requires a current TOTP code so an attacker with a stolen session
    can't silently swap the codes the legitimate user wrote down."""
    user = _get_user_or_404(db, current_user)
    enrollment = mfa_service.get_enrollment(db, user.id)
    if enrollment is None:
        raise HTTPException(
            status_code=400,
            detail=_("MFA is not enrolled for this account."),
        )
    settings = mfa_service.get_settings(db)
    secret = mfa_service.decrypt_secret(enrollment.totp_secret_encrypted)
    if not mfa_service.verify_totp(secret, request.code, settings):
        _audit(
            db,
            user,
            "MFA backup-code regen rejected",
            success=False,
            details={"reason": "invalid_totp_code"},
        )
        raise HTTPException(status_code=401, detail=_("Invalid TOTP code."))
    plaintext = mfa_service.generate_backup_codes(settings.backup_code_count)
    enrollment.backup_codes_hashed = mfa_service.hash_backup_codes(plaintext)
    db.commit()
    _audit(
        db,
        user,
        "MFA backup codes regenerated",
        success=True,
        details={"backup_code_count": len(plaintext)},
    )
    return EnrollCompleteResponse(
        backup_codes=plaintext,
        enrolled_at=(
            enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else ""
        ),
    )


# ---------------------------------------------------------------------
# Admin settings
# ---------------------------------------------------------------------


@router.get("/api/settings/mfa", dependencies=[Depends(JWTBearer())])
async def get_mfa_settings(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Return the singleton MFA settings row.  Visible to any
    authenticated user so the login UI / profile page can read the
    issuer name + grace policy without an admin role."""
    return mfa_service.get_settings(db).to_dict()


@router.put("/api/settings/mfa", dependencies=[Depends(JWTBearer())])
async def update_mfa_settings(
    request: MfaSettingsRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Update the singleton MFA settings.  Admin-only.

    The list of fields is a controlled subset — we don't expose
    ``updated_at`` or ``updated_by`` to the request schema.
    """
    user = _get_user_or_404(db, current_user)
    if not _user_has_role(db, user, SecurityRoles.EDIT_USER_SECURITY_ROLES):
        raise HTTPException(
            status_code=403,
            detail=_("Editing MFA settings requires admin privileges."),
        )
    settings = mfa_service.get_settings(db)
    # If we got the transient fallback row, persist it before mutating.
    if settings not in db:
        db.add(settings)
    if request.issuer_name is not None:
        settings.issuer_name = request.issuer_name
    if request.totp_digits is not None:
        settings.totp_digits = request.totp_digits
    if request.totp_period_seconds is not None:
        settings.totp_period_seconds = request.totp_period_seconds
    if request.backup_code_count is not None:
        settings.backup_code_count = request.backup_code_count
    if request.admin_required is not None:
        settings.admin_required = request.admin_required
    if request.grace_period_days is not None:
        settings.grace_period_days = request.grace_period_days
    settings.updated_by = user.id
    db.commit()
    db.refresh(settings)
    _audit(db, user, "MFA settings updated", success=True)
    return settings.to_dict()


def _user_has_role(db: Session, user: models.User, role: SecurityRoles) -> bool:
    """Return True if ``user`` has the given role.  Mirrors the per-user
    role-cache pattern used elsewhere in the codebase."""
    # pylint: disable=import-outside-toplevel
    from backend.security.roles import load_user_roles

    return load_user_roles(db, user.id).has_role(role)
