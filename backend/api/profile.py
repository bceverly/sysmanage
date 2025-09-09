"""
This module houses the API routes for user profile management in SysManage.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pyargon2 import hash as argon2_hash
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.config import config
from backend.i18n import _
from backend.persistence import db, models
from backend.utils.password_policy import password_policy

router = APIRouter()


class ProfileUpdate(BaseModel):
    """
    This class represents the JSON payload for updating user profile.
    """

    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ProfileResponse(BaseModel):
    """
    This class represents the JSON response for user profile.
    """

    userid: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    active: bool
    password_requirements: str


class PasswordChange(BaseModel):
    """
    This class represents the JSON payload for changing user password.
    """

    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(
        ..., min_length=8, description="New password (minimum 8 characters)"
    )
    confirm_password: str = Field(..., min_length=1, description="Confirm new password")


@router.get("/profile", dependencies=[Depends(JWTBearer())])
async def get_profile(current_user: str = Depends(get_current_user)):
    """
    Get the current user's profile information.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the user by userid
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )

        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        return ProfileResponse(
            userid=user.userid,
            first_name=user.first_name,
            last_name=user.last_name,
            active=user.active,
            password_requirements=password_policy.get_requirements_text(),
        )


@router.put("/profile", dependencies=[Depends(JWTBearer())])
async def update_profile(
    profile_data: ProfileUpdate, current_user: str = Depends(get_current_user)
):
    """
    Update the current user's profile information.
    """
    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the user by userid
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )

        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Update the fields if explicitly provided (including None values)
        # Using model_dump to check which fields were actually provided in the request
        update_dict = profile_data.model_dump(exclude_unset=True)
        if "first_name" in update_dict:
            user.first_name = profile_data.first_name
        if "last_name" in update_dict:
            user.last_name = profile_data.last_name

        # Update last access
        user.last_access = datetime.now(timezone.utc)

        session.commit()
        session.refresh(user)

        return ProfileResponse(
            userid=user.userid,
            first_name=user.first_name,
            last_name=user.last_name,
            active=user.active,
            password_requirements=password_policy.get_requirements_text(),
        )


@router.put("/profile/password", dependencies=[Depends(JWTBearer())])
async def change_password(
    password_data: PasswordChange, current_user: str = Depends(get_current_user)
):
    """
    Change the current user's password.
    """
    # Validate new password confirmation
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=400, detail=_("New password and confirmation do not match")
        )

    # Validate password against policy
    is_valid, validation_errors = password_policy.validate_password(
        password_data.new_password, current_user
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="; ".join(validation_errors))

    # Get the current configuration
    the_config = config.get_config()
    password_salt = the_config["security"]["password_salt"]

    # Get the SQLAlchemy session
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db.get_engine()
    )

    with session_local() as session:
        # Find the user by userid
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )

        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Verify current password
        current_password_hash = argon2_hash(
            password_data.current_password, password_salt
        )
        if user.hashed_password != current_password_hash:
            raise HTTPException(
                status_code=400, detail=_("Current password is incorrect")
            )

        # Hash new password
        new_password_hash = argon2_hash(password_data.new_password, password_salt)

        # Update password and last access time
        user.hashed_password = new_password_hash
        user.last_access = datetime.now(timezone.utc)

        session.commit()

        return {"message": _("Password changed successfully")}
