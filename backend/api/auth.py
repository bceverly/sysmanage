"""
This module provides the necessary function to support login to the SysManage
server.
"""

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.auth.auth_handler import (
    decode_jwt,
    sign_jwt,
    sign_mfa_pending_token,
    sign_refresh_token,
)
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.security.login_security import login_security
from backend.services import mfa_service
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

argon2_hasher = PasswordHasher()

router = APIRouter()


def _invalid_credentials_error() -> HTTPException:
    """The single source of truth for the generic-401 used on every
    auth-failure path (unknown user, wrong password, inactive account,
    rate-limit miss, etc.).  Returning the same wording from every
    branch is a deliberate security choice — leaking which input was
    wrong helps account enumeration.

    Kept as a function rather than a module-level constant so the
    ``_(...)`` call site sees a string literal at extraction time;
    babel/gettext can't pull strings out of variable references."""
    return HTTPException(status_code=401, detail=_("Invalid username or password"))


def _is_secure_cookie_enabled(the_config):
    """Determine if secure cookies should be used based on config."""
    cert_file = the_config.get("api", {}).get("certFile")
    return cert_file is not None and len(cert_file) > 0


def _set_refresh_cookie(response, refresh_token, jwt_refresh_timeout, is_secure):
    """Set the refresh token cookie on the response.

    The cookie's Domain attribute is taken from `security.cookie_domain` in
    the YAML configuration. If that key is unset (the default), the Domain
    attribute is omitted entirely and the cookie is scoped to the host that
    served the response — RFC 6265's default behavior, and what most
    deployments want. Setting an explicit domain that doesn't match the
    request host (e.g. hard-coding 'sysmanage.org' on a localhost dev box)
    causes RFC-compliant clients to reject the cookie outright; this used
    to produce 'invalid cookie' errors in local load testing and against
    any non-sysmanage.org deployment.
    """
    cookie_domain = config.get_config().get("security", {}).get("cookie_domain")
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc) + timedelta(seconds=jwt_refresh_timeout),
        path="/",
        domain=cookie_domain,
        secure=is_secure,
        httponly=True,
        samesite="strict" if is_secure else "lax",
    )


def _log_login_attempt(
    session, user_id, username, success, client_ip, user_agent, error_msg=None
):
    """Log a login attempt to the audit log."""
    AuditService.log(
        db=session,
        user_id=user_id,
        username=username,
        action_type=ActionType.LOGIN,
        entity_type=EntityType.USER,
        entity_id=str(user_id) if user_id else None,
        entity_name=username,
        description=f"{'Successful' if success else 'Failed'} login attempt for user {username}"
        + (f" - {error_msg}" if error_msg and not success else ""),
        result=Result.SUCCESS if success else Result.FAILURE,
        error_message=error_msg if not success else None,
        ip_address=client_ip,
        user_agent=user_agent,
    )


class UserLogin(BaseModel):
    """
    This class represents the JSON payload to the /login POST request.
    """

    userid: EmailStr
    password: str


@router.post("/login")
async def login(login_data: UserLogin, request: Request, response: Response):  # NOSONAR
    """
    This function provides login ability to the SysManage server with enhanced security.
    """
    # Get client information for security logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Validate login attempt against security policies
    is_allowed, reason = login_security.validate_login_attempt(
        str(login_data.userid), client_ip
    )
    if not is_allowed:
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )
        raise HTTPException(status_code=429, detail=_(reason))

    the_config = config.get_config()
    db.get_db()
    jwt_refresh_timeout = int(
        the_config.get("security", {}).get("jwt_refresh_timeout", 86400)
    )
    is_secure = _is_secure_cookie_enabled(the_config)

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Try admin credentials first
    admin_result = _try_admin_login(
        login_data,
        the_config,
        session_local,
        client_ip,
        user_agent,
        response,
        jwt_refresh_timeout,
        is_secure,
    )
    if admin_result:
        return admin_result

    # Try database user authentication
    with session_local() as session:
        user = (
            session.query(models.User)
            .filter(models.User.userid == login_data.userid)
            .first()
        )

        if user:
            return _authenticate_db_user(
                user,
                login_data,
                session,
                the_config,
                client_ip,
                user_agent,
                response,
                jwt_refresh_timeout,
                is_secure,
            )

        # User not found - still record failed attempt for security
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )

    raise _invalid_credentials_error()


def _try_admin_login(
    login_data,
    the_config,
    session_local,
    client_ip,
    user_agent,
    response,
    jwt_refresh_timeout,
    is_secure,
):
    """Try to authenticate using admin credentials from config file."""
    admin_userid = the_config.get("security", {}).get("admin_userid")
    admin_password = the_config.get("security", {}).get("admin_password")

    if not (admin_userid and admin_password and login_data.userid == admin_userid):
        return None

    if login_data.password != admin_password:
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )
        with session_local() as audit_session:
            _log_login_attempt(
                audit_session,
                None,
                str(login_data.userid),
                False,
                client_ip,
                user_agent,
                "Invalid password",
            )
        return None

    # Successful admin login
    login_security.record_successful_login(
        str(login_data.userid), client_ip, user_agent
    )
    with session_local() as audit_session:
        _log_login_attempt(
            audit_session, None, str(login_data.userid), True, client_ip, user_agent
        )

    refresh_token = sign_refresh_token(login_data.userid)
    _set_refresh_cookie(response, refresh_token, jwt_refresh_timeout, is_secure)
    return {"Authorization": sign_jwt(login_data.userid)}


def _authenticate_db_user(  # NOSONAR
    user,
    login_data,
    session,
    _the_config,  # noqa: ARG001 - kept for API consistency with _try_admin_login
    client_ip,
    user_agent,
    response,
    jwt_refresh_timeout,
    is_secure,
):
    """Authenticate a user from the database."""
    # Reject inactive accounts before any lockout / password work.  We
    # respond with the same generic 401 + "Invalid username or password"
    # message used for wrong-password and unknown-user paths so an
    # attacker cannot probe whether a given userid exists-but-disabled
    # vs. doesn't-exist.  The audit trail still records the disabled
    # account login attempt for the operator.
    if not user.active:
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )
        _log_login_attempt(
            session,
            user.id,
            str(login_data.userid),
            False,
            client_ip,
            user_agent,
            "Account is inactive",
        )
        raise _invalid_credentials_error()

    # Check if user account is locked
    if login_security.is_user_account_locked(user):
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )
        raise HTTPException(
            status_code=423,
            detail=_("Account is locked due to too many failed login attempts"),
        )

    # Phase 10.5 — external IdP path.  Users with a non-NULL
    # ``external_idp_provider_id`` authenticate against the directory
    # via the Pro+ ``external_idp_engine``.  Three outcomes:
    #   * engine accepts → skip Argon2, proceed to the post-password
    #     branch (MFA challenge / session token / etc.)
    #   * engine declines AND ``local_account_fallback`` disabled →
    #     reject with the usual lockout-counter increment.
    #   * engine declines but fallback enabled, OR engine not loaded →
    #     fall through to local Argon2 verify (break-glass).
    idp_auth_passed = False
    if getattr(user, "external_idp_provider_id", None):
        idp_outcome = _try_external_idp_auth(user, login_data, session)
        if idp_outcome is True:
            idp_auth_passed = True
        elif idp_outcome is False:
            idp_settings = (
                session.query(models.ExternalIdpSettings)
                .filter(
                    models.ExternalIdpSettings.id == models.SINGLETON_IDP_SETTINGS_ID
                )
                .first()
            )
            if not idp_settings or not idp_settings.local_account_fallback:
                return _handle_failed_password(
                    user, login_data, session, client_ip, user_agent
                )
        # else idp_outcome is None → engine not loaded; fall through.

    # Verify password (skipped when external IdP already accepted).
    if not idp_auth_passed:
        try:
            argon2_hasher.verify(user.hashed_password, login_data.password)
        except Exception:  # catches argon2 verification failures
            return _handle_failed_password(
                user, login_data, session, client_ip, user_agent
            )

    # Password OK from here on — but a second factor may still gate
    # the actual session token.  Three branches:
    #
    #   a) User has MFA enrolled → issue a short-lived ``mfa_pending``
    #      token; the client follows up with /api/auth/mfa/verify.
    #   b) Admin required MFA AND user is past the grace period →
    #      refuse with a structured error so the UI can prompt enroll.
    #   c) Otherwise (no MFA enrolled, no policy gate) → issue a real
    #      session token, matching pre-Phase-10.3 behaviour.
    enrollment = mfa_service.get_enrollment(session, user.id)
    if enrollment is not None:
        # Record the password-OK event before issuing the pending token
        # so the audit log shows where the second factor came in.
        _log_login_attempt(
            session,
            user.id,
            str(login_data.userid),
            True,
            client_ip,
            user_agent,
            error_msg="MFA challenge issued",
        )
        login_security.record_successful_login(
            str(login_data.userid), client_ip, user_agent
        )
        login_security.reset_failed_login_attempts(user, session)
        session.commit()
        return {
            "mfa_required": True,
            "pending_token": sign_mfa_pending_token(login_data.userid),
        }

    mfa_settings = mfa_service.get_settings(session)
    if mfa_settings.admin_required:
        grace_cutoff = user.created_at + timedelta(days=mfa_settings.grace_period_days)
        if datetime.now(timezone.utc).replace(tzinfo=None) > grace_cutoff:
            _log_login_attempt(
                session,
                user.id,
                str(login_data.userid),
                False,
                client_ip,
                user_agent,
                error_msg="MFA enrollment required (grace period expired)",
            )
            session.commit()
            raise HTTPException(
                status_code=403,
                detail=_(
                    "Multi-factor authentication is required for this account. "
                    "Please enrol from your profile page before signing in."
                ),
            )

    # Successful login (no MFA enrolled, or admin-required policy hasn't
    # passed the grace cutoff yet).
    login_security.record_successful_login(
        str(login_data.userid), client_ip, user_agent
    )
    login_security.reset_failed_login_attempts(user, session)
    user.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
    session.commit()

    _log_login_attempt(
        session, user.id, str(login_data.userid), True, client_ip, user_agent
    )

    auth_token = sign_jwt(login_data.userid)
    refresh_token = sign_refresh_token(login_data.userid)
    _set_refresh_cookie(response, refresh_token, jwt_refresh_timeout, is_secure)
    return {"Authorization": auth_token}


def _try_external_idp_auth(user, login_data, session):
    """Authenticate ``user`` against their configured external IdP.

    Returns ``True`` when the engine accepts the password (LDAP bind
    succeeded), ``False`` when it declines, ``None`` when the engine
    isn't loaded (caller falls back to local Argon2).

    Currently only handles LDAP — OIDC users go through the
    /api/auth/oidc/{provider}/callback endpoint, not the password
    login form.
    """
    # pylint: disable=import-outside-toplevel
    from backend.licensing.module_loader import module_loader

    engine = module_loader.get_module("external_idp_engine")
    if engine is None:
        return None
    provider = (
        session.query(models.ExternalIdpProvider)
        .filter(models.ExternalIdpProvider.id == user.external_idp_provider_id)
        .first()
    )
    if not provider or not provider.enabled or provider.type != "ldap":
        return None
    config = provider.to_dict()
    # Resolve bind password from Vault before passing to the engine.
    from backend.api.external_idp import (
        _resolve_secret,
    )  # pylint: disable=import-outside-toplevel

    config["ldap_bind_password"] = _resolve_secret(
        provider.ldap_bind_password_secret_id
    )
    try:
        result = engine.authenticate_ldap(
            config, str(login_data.userid), login_data.password
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Engine raised — treat as decline so the local fallback can
        # kick in if the operator has it enabled.
        return False
    return bool(result.get("success"))


def _handle_failed_password(user, login_data, session, client_ip, user_agent):
    """Handle failed password verification."""
    login_security.record_failed_login(str(login_data.userid), client_ip, user_agent)
    account_locked = login_security.record_failed_login_for_user(user, session)

    error_suffix = " - account locked" if account_locked else ""
    _log_login_attempt(
        session,
        user.id,
        str(login_data.userid),
        False,
        client_ip,
        user_agent,
        f"Invalid password{error_suffix}",
    )

    if account_locked:
        raise HTTPException(
            status_code=423,
            detail=_("Account locked due to too many failed login attempts"),
        )

    raise _invalid_credentials_error()


@router.post("/refresh")
async def refresh(request: Request):
    """
    This API call looks for refresh token passed in the cookies of the
    request as an http_only cookie (inaccessible to the client).  If present,
    a new JWT Authentication token will be generated and returned.  If not,
    then a 403 - Forbidden error will be returned, forcing the client to
    re-authenticate via a user-managed login.
    """
    if request.cookies and "refresh_token" in request.cookies:
        refresh_token = request.cookies["refresh_token"]
        token_dict = decode_jwt(refresh_token)
        if token_dict:
            the_userid = token_dict["user_id"]
            # Preserve the active tenant across a refresh (13.1.B); None in
            # single-tenant mode, so the token shape is unchanged there.
            the_tenant = token_dict.get("tenant_id")
            new_token = sign_jwt(the_userid, tenant_id=the_tenant)
            return {"Authorization": new_token}

    raise HTTPException(status_code=403, detail=_("Invalid or missing refresh token"))


class SwitchAccountRequest(BaseModel):
    """Body for ``POST /api/auth/switch-account``."""

    tenant_id: str


def _open_registry_session():
    """Open a session on the registry partition (late import avoids cycles)."""
    from backend.persistence.partitions import (  # noqa: PLC0415
        PARTITION_REGISTRY,
        get_sessionmaker,
    )

    return get_sessionmaker(partition=PARTITION_REGISTRY)()


@router.get("/auth/accounts", dependencies=[Depends(JWTBearer())])
async def list_accounts(current_user: str = Depends(get_current_user)):
    """List the tenants the current user can switch to (their live grants).

    Multi-tenancy only — returns 400 when the feature is disabled.
    """
    if not config.is_multitenancy_enabled():
        raise HTTPException(status_code=400, detail=_("Multi-tenancy is not enabled."))

    from backend.persistence.models.tenancy import RegistryTenant  # noqa: PLC0415
    from backend.services import registry_service  # noqa: PLC0415

    session = _open_registry_session()
    try:
        grants = registry_service.list_user_grants(session, current_user)
        accounts = []
        for grant in grants:
            tenant = (
                session.query(RegistryTenant)
                .filter(RegistryTenant.id == grant.tenant_id)
                .first()
            )
            if tenant:
                accounts.append(
                    {
                        "tenant_id": str(tenant.id),
                        "name": tenant.name,
                        "slug": tenant.slug,
                        "role": grant.role,
                        "is_default": grant.is_default,
                    }
                )
        return {"accounts": accounts, "total": len(accounts)}
    finally:
        session.close()


@router.post("/auth/switch-account", dependencies=[Depends(JWTBearer())])
async def switch_account(
    payload: SwitchAccountRequest,
    response: Response,
    current_user: str = Depends(get_current_user),
):
    """Switch the active tenant and re-mint the token to carry it.

    Verifies the caller holds a live grant to the requested tenant before
    re-minting both the access token and the refresh cookie with the new
    ``tenant_id``.  Multi-tenancy only (400 when disabled).
    """
    if not config.is_multitenancy_enabled():
        raise HTTPException(status_code=400, detail=_("Multi-tenancy is not enabled."))

    from backend.services import registry_service  # noqa: PLC0415

    session = _open_registry_session()
    try:
        if not registry_service.has_active_grant(
            session, current_user, payload.tenant_id
        ):
            raise HTTPException(
                status_code=403,
                detail=_("You do not have access to the selected account."),
            )
    finally:
        session.close()

    the_config = config.get_config()
    jwt_refresh_timeout = int(
        the_config.get("security", {}).get("jwt_refresh_timeout", 86400)
    )
    is_secure = _is_secure_cookie_enabled(the_config)

    refresh_token = sign_refresh_token(current_user, tenant_id=payload.tenant_id)
    _set_refresh_cookie(response, refresh_token, jwt_refresh_timeout, is_secure)
    return {"Authorization": sign_jwt(current_user, tenant_id=payload.tenant_id)}


@router.post("/logout", dependencies=[Depends(JWTBearer())])
async def logout(request: Request, current_user: str = Depends(get_current_user)):
    """
    Log user logout for audit purposes.
    The actual logout is handled client-side by discarding the JWT token.
    """
    # Get client information for audit logging
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Get user for audit logging
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )

        if user:
            # Log the logout
            AuditService.log(
                db=session,
                user_id=user.id,
                username=current_user,
                action_type=ActionType.LOGOUT,
                entity_type=EntityType.AUTHENTICATION,
                entity_id=str(user.id),
                entity_name=current_user,
                description=f"User {current_user} logged out",
                result=Result.SUCCESS,
                ip_address=client_ip,
                user_agent=user_agent,
            )

    return {"message": _("Logout successful")}
