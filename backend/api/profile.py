"""
This module houses the API routes for user profile management in SysManage.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models

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
        )
