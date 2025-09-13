"""
This module houses the API routes for user profile management in SysManage.
"""

import io
from datetime import datetime, timezone
from typing import Optional

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.utils.password_policy import password_policy

argon2_hasher = PasswordHasher()

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
    has_profile_image: bool = False
    profile_image_uploaded_at: Optional[datetime] = None


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
            has_profile_image=user.profile_image is not None,
            profile_image_uploaded_at=user.profile_image_uploaded_at,
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
            has_profile_image=user.profile_image is not None,
            profile_image_uploaded_at=user.profile_image_uploaded_at,
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

        # Verify current password using argon2-cffi
        try:
            argon2_hasher.verify(user.hashed_password, password_data.current_password)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=_("Current password is incorrect")
            ) from exc

        # Hash new password
        new_password_hash = argon2_hasher.hash(password_data.new_password)

        # Update password and last access time
        user.hashed_password = new_password_hash
        user.last_access = datetime.now(timezone.utc)

        session.commit()

        return {"message": _("Password changed successfully")}


# Security configuration for image uploads
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB limit to prevent DoS attacks
ALLOWED_FORMATS = {"PNG", "JPEG", "JPG", "GIF", "WEBP"}
MAX_DIMENSIONS = (512, 512)  # Maximum width and height in pixels


def validate_and_process_image(file_content: bytes, filename: str) -> tuple[bytes, str]:
    """
    Validate and process uploaded image with security controls.

    Args:
        file_content: The raw file bytes
        filename: Original filename for format detection

    Returns:
        Tuple of (processed_image_bytes, format)

    Raises:
        HTTPException: If validation fails
    """
    # Check file size to prevent DoS attacks
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=_("File size too large. Maximum allowed size is 5MB."),
        )

    try:
        # Open and validate the image
        image = Image.open(io.BytesIO(file_content))

        # Verify it's a valid image format
        if image.format not in ALLOWED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=_(
                    "Unsupported image format. Allowed formats: PNG, JPEG, JPG, GIF, WEBP"
                ),
            )

        # Convert RGBA to RGB for JPEG compatibility
        if image.mode in ("RGBA", "LA", "P"):
            # Create a white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(
                image, mask=image.split()[-1] if image.mode == "RGBA" else None
            )
            image = background

        # Resize image if it exceeds maximum dimensions
        if image.size[0] > MAX_DIMENSIONS[0] or image.size[1] > MAX_DIMENSIONS[1]:
            image.thumbnail(MAX_DIMENSIONS, Image.Resampling.LANCZOS)

        # Convert to bytes with consistent format (PNG for best quality with transparency support)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="PNG", optimize=True)
        img_bytes.seek(0)

        return img_bytes.getvalue(), "png"

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=400,
            detail=_("Invalid image file. Please upload a valid image."),
        ) from e


@router.post("/profile/image", dependencies=[Depends(JWTBearer())])
async def upload_profile_image(
    file: UploadFile = File(...), current_user: str = Depends(get_current_user)
):
    """
    Upload a profile image for the current user.

    Security features:
    - File size limit (5MB) to prevent DoS attacks
    - Image format validation
    - Automatic resizing to prevent excessive storage usage
    - Image processing to ensure valid image data
    """
    # Validate file is provided
    if not file:
        raise HTTPException(status_code=400, detail=_("No file provided"))

    # Read file content
    try:
        file_content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=_("Error reading uploaded file")
        ) from exc

    # Validate and process the image
    processed_image_bytes, image_format = validate_and_process_image(
        file_content, file.filename or "image"
    )

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

        # Update user's profile image
        user.profile_image = processed_image_bytes
        user.profile_image_type = image_format
        user.profile_image_uploaded_at = datetime.now(timezone.utc)
        user.last_access = datetime.now(timezone.utc)

        session.commit()

        return {
            "message": _("Profile image uploaded successfully"),
            "image_format": image_format,
            "uploaded_at": user.profile_image_uploaded_at,
        }


@router.get("/profile/image", dependencies=[Depends(JWTBearer())])
async def get_profile_image(current_user: str = Depends(get_current_user)):
    """
    Get the current user's profile image.
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

        if not user.profile_image:
            raise HTTPException(status_code=404, detail=_("No profile image found"))

        # Determine content type based on stored format
        content_type = f"image/{user.profile_image_type}"
        if user.profile_image_type == "jpg":
            content_type = "image/jpeg"

        return Response(
            content=user.profile_image,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Last-Modified": user.profile_image_uploaded_at.strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                ),
            },
        )


@router.delete("/profile/image", dependencies=[Depends(JWTBearer())])
async def delete_profile_image(current_user: str = Depends(get_current_user)):
    """
    Delete the current user's profile image.
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

        if not user.profile_image:
            raise HTTPException(status_code=404, detail=_("No profile image to delete"))

        # Clear the profile image data
        user.profile_image = None
        user.profile_image_type = None
        user.profile_image_uploaded_at = None
        user.last_access = datetime.now(timezone.utc)

        session.commit()

        return {"message": _("Profile image deleted successfully")}
