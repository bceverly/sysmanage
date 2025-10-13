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


class UserLogin(BaseModel):
    """
    This class represents the JSON payload to the /login POST request.
    """

    userid: EmailStr
    password: str


@router.post("/login")
async def login(login_data: UserLogin, request: Request, response: Response):
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
    # Get the /etc/sysmanage.yaml configuration
    the_config = config.get_config()

    db.get_db()
    success = False

    # Check YAML admin credentials only if they are configured
    admin_userid = the_config.get("security", {}).get("admin_userid")
    admin_password = the_config.get("security", {}).get("admin_password")

    if admin_userid and admin_password and login_data.userid == admin_userid:
        if login_data.password == admin_password:
            success = True

            # Record successful login
            login_security.record_successful_login(
                str(login_data.userid), client_ip, user_agent
            )

            # Audit log successful admin login
            with session_local() as audit_session:
                AuditService.log(
                    db=audit_session,
                    action_type=ActionType.LOGIN,
                    entity_type=EntityType.USER,
                    entity_name=str(login_data.userid),
                    description=f"Admin user {login_data.userid} logged in successfully",
                    result=Result.SUCCESS,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )

            refresh_token = sign_refresh_token(login_data.userid)
            jwt_refresh_timout = int(the_config["security"]["jwt_refresh_timeout"])

            # Determine if we should use secure cookies based on config
            is_secure = (
                the_config.get("api", {}).get("certFile") is not None
                and len(the_config.get("api", {}).get("certFile", "")) > 0
            )

            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                expires=datetime.now(timezone.utc)
                + timedelta(seconds=jwt_refresh_timout),
                path="/",
                domain="sysmanage.org",
                secure=is_secure,
                httponly=True,
                samesite="strict" if is_secure else "lax",
            )
            return {"Authorization": sign_jwt(login_data.userid)}

        # Record failed admin login attempt
        if not success:
            login_security.record_failed_login(
                str(login_data.userid), client_ip, user_agent
            )
            # Audit log failed admin login
            with session_local() as audit_session:
                AuditService.log(
                    db=audit_session,
                    action_type=ActionType.LOGIN,
                    entity_type=EntityType.USER,
                    entity_name=str(login_data.userid),
                    description=f"Failed login attempt for admin user {login_data.userid}",
                    result=Result.FAILURE,
                    error_message="Invalid password",
                    ip_address=client_ip,
                    user_agent=user_agent,
                )

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    # Check if this is a valid user
    with session_local() as session:
        # Query for the specific user
        user = (
            session.query(models.User)
            .filter(models.User.userid == login_data.userid)
            .first()
        )

        if user:
            # Check if user account is locked
            if login_security.is_user_account_locked(user):
                login_security.record_failed_login(
                    str(login_data.userid), client_ip, user_agent
                )
                raise HTTPException(
                    status_code=423,
                    detail=_("Account is locked due to too many failed login attempts"),
                )

            # Verify password using argon2-cffi
            try:
                argon2_hasher.verify(user.hashed_password, login_data.password)
                success = True

                # Record successful login and reset failed attempts
                login_security.record_successful_login(
                    str(login_data.userid), client_ip, user_agent
                )
                login_security.reset_failed_login_attempts(user, session)

                # Update the last access datetime
                user.last_access = datetime.now(timezone.utc).replace(tzinfo=None)
                session.commit()

                # Audit log successful user login
                AuditService.log(
                    db=session,
                    user_id=user.id,
                    username=str(login_data.userid),
                    action_type=ActionType.LOGIN,
                    entity_type=EntityType.USER,
                    entity_id=str(user.id),
                    entity_name=str(login_data.userid),
                    description=f"User {login_data.userid} logged in successfully",
                    result=Result.SUCCESS,
                    ip_address=client_ip,
                    user_agent=user_agent,
                )

                # Add the refresh token to an http-only cookie
                auth_token = sign_jwt(login_data.userid)
                refresh_token = sign_refresh_token(login_data.userid)
                jwt_refresh_timout = int(the_config["security"]["jwt_refresh_timeout"])

                # Determine if we should use secure cookies based on config
                is_secure = (
                    the_config.get("api", {}).get("certFile") is not None
                    and len(the_config.get("api", {}).get("certFile", "")) > 0
                )

                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    expires=datetime.now(timezone.utc)
                    + timedelta(seconds=jwt_refresh_timout),
                    path="/",
                    domain="sysmanage.org",
                    secure=is_secure,
                    httponly=True,
                    samesite="strict" if is_secure else "lax",
                )

                # Return success
                return {"Authorization": auth_token}
            except Exception:  # nosec B110
                # Wrong password - record failed attempt and potentially lock account
                pass

            # Wrong password - record failed attempt and potentially lock account
            login_security.record_failed_login(
                str(login_data.userid), client_ip, user_agent
            )
            account_locked = login_security.record_failed_login_for_user(user, session)

            # Audit log failed login
            AuditService.log(
                db=session,
                user_id=user.id,
                username=str(login_data.userid),
                action_type=ActionType.LOGIN,
                entity_type=EntityType.USER,
                entity_id=str(user.id),
                entity_name=str(login_data.userid),
                description=f"Failed login attempt for user {login_data.userid}"
                + (" - account locked" if account_locked else ""),
                result=Result.FAILURE,
                error_message="Invalid password"
                + (" - account locked" if account_locked else ""),
                ip_address=client_ip,
                user_agent=user_agent,
            )

            if account_locked:
                raise HTTPException(
                    status_code=423,
                    detail=_("Account locked due to too many failed login attempts"),
                )
        else:
            # User not found - still record failed attempt for security
            login_security.record_failed_login(
                str(login_data.userid), client_ip, user_agent
            )

    # If we got here, then there was no match
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
    if len(request.cookies) > 0:
        if "refresh_token" in request.cookies:
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
