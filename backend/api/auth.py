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
from backend.auth.auth_handler import decode_jwt, sign_jwt, sign_refresh_token
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.security.login_security import login_security
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

argon2_hasher = PasswordHasher()

router = APIRouter()


def _is_secure_cookie_enabled(the_config):
    """Determine if secure cookies should be used based on config."""
    cert_file = the_config.get("api", {}).get("certFile")
    return cert_file is not None and len(cert_file) > 0


def _set_refresh_cookie(response, refresh_token, jwt_refresh_timeout, is_secure):
    """Set the refresh token cookie on the response."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc) + timedelta(seconds=jwt_refresh_timeout),
        path="/",
        domain="sysmanage.org",
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
    jwt_refresh_timeout = int(the_config["security"]["jwt_refresh_timeout"])
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

    raise HTTPException(status_code=401, detail=_("Invalid username or password"))


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


def _authenticate_db_user(
    user,
    login_data,
    session,
    the_config,
    client_ip,
    user_agent,
    response,
    jwt_refresh_timeout,
    is_secure,
):
    """Authenticate a user from the database."""
    # Check if user account is locked
    if login_security.is_user_account_locked(user):
        login_security.record_failed_login(
            str(login_data.userid), client_ip, user_agent
        )
        raise HTTPException(
            status_code=423,
            detail=_("Account is locked due to too many failed login attempts"),
        )

    # Verify password
    try:
        argon2_hasher.verify(user.hashed_password, login_data.password)
    except Exception:  # nosec B110 - catches argon2 verification failures
        return _handle_failed_password(user, login_data, session, client_ip, user_agent)

    # Successful login
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

    raise HTTPException(status_code=401, detail=_("Invalid username or password"))


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
            new_token = sign_jwt(the_userid)
            return {"Authorization": new_token}

    raise HTTPException(status_code=403, detail="Invalid or missing refresh token")


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
