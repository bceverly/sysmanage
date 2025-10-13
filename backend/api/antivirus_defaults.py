"""
This module houses the API routes for antivirus default settings management in SysManage.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result

logger = logging.getLogger(__name__)

router = APIRouter()


class AntivirusDefaultResponse(BaseModel):
    """Response model for antivirus default."""

    id: str
    os_name: str
    antivirus_package: str
    created_at: datetime
    updated_at: datetime

    @validator("id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class AntivirusDefaultUpdate(BaseModel):
    """Request model for updating antivirus defaults."""

    os_name: str
    antivirus_package: Optional[str] = None

    @validator("os_name")
    def validate_os_name(cls, os_name):  # pylint: disable=no-self-argument
        """Validate OS name."""
        if not os_name or os_name.strip() == "":
            raise ValueError(_("OS name is required"))
        if len(os_name) > 100:
            raise ValueError(_("OS name must be 100 characters or less"))
        return os_name.strip()

    @validator("antivirus_package")
    def validate_antivirus_package(
        cls, antivirus_package
    ):  # pylint: disable=no-self-argument
        """Validate antivirus package."""
        if antivirus_package is not None:
            if antivirus_package.strip() == "":
                return None
            if len(antivirus_package) > 255:
                raise ValueError(
                    _("Antivirus package name must be 255 characters or less")
                )
            return antivirus_package.strip()
        return antivirus_package


class AntivirusDefaultsBulkUpdate(BaseModel):
    """Request model for bulk updating antivirus defaults."""

    defaults: List[AntivirusDefaultUpdate]


@router.get("/", response_model=List[AntivirusDefaultResponse])
async def get_antivirus_defaults(
    db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Get all antivirus defaults."""
    try:
        defaults = db.query(models.AntivirusDefault).all()
        return defaults

    except Exception as e:
        logger.error("Error getting antivirus defaults: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve antivirus defaults: %s") % str(e),
        ) from e


@router.get("/{os_name}", response_model=AntivirusDefaultResponse)
async def get_antivirus_default_for_os(
    os_name: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Get antivirus default for a specific OS."""
    try:
        default = (
            db.query(models.AntivirusDefault)
            .filter(models.AntivirusDefault.os_name == os_name)
            .first()
        )

        if not default:
            raise HTTPException(
                status_code=404,
                detail=_("No antivirus default found for OS: %s") % os_name,
            )

        return default

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting antivirus default for OS %s: %s", os_name, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve antivirus default: %s") % str(e),
        ) from e


@router.put("/", response_model=List[AntivirusDefaultResponse])
async def update_antivirus_defaults(
    bulk_update: AntivirusDefaultsBulkUpdate,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Update antivirus defaults (bulk operation)."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        # Check if user has permission to manage antivirus defaults
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.MANAGE_ANTIVIRUS_DEFAULTS):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: MANAGE_ANTIVIRUS_DEFAULTS role required"),
            )

    try:
        updated_defaults = []

        for update in bulk_update.defaults:
            # Find existing default for this OS
            default = (
                db_session.query(models.AntivirusDefault)
                .filter(models.AntivirusDefault.os_name == update.os_name)
                .first()
            )

            now = datetime.now(timezone.utc).replace(tzinfo=None)

            if not default:
                # Create new default if it doesn't exist
                if update.antivirus_package:
                    default = models.AntivirusDefault(
                        os_name=update.os_name,
                        antivirus_package=update.antivirus_package,
                        created_at=now,
                        updated_at=now,
                    )
                    db_session.add(default)
                    updated_defaults.append(default)
            else:
                # Update existing default
                if update.antivirus_package:
                    default.antivirus_package = update.antivirus_package
                    default.updated_at = now
                    updated_defaults.append(default)
                else:
                    # If package is None or empty, delete the default
                    db_session.delete(default)

        db_session.commit()

        # Refresh all updated defaults
        for default in updated_defaults:
            db_session.refresh(default)

        logger.info(
            "Antivirus defaults updated: %d records",
            len(updated_defaults),
        )

        # Log audit entry for each updated default
        for default in updated_defaults:
            AuditService.log_update(
                db=db_session,
                entity_type=EntityType.SETTING,
                entity_name=f"Antivirus Default for {default.os_name}",
                user_id=auth_user.id,
                username=current_user,
                entity_id=str(default.id),
                details={
                    "os_name": default.os_name,
                    "antivirus_package": default.antivirus_package,
                },
            )

        return updated_defaults

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error updating antivirus defaults: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to update antivirus defaults: %s") % str(e),
        ) from e


@router.delete("/{os_name}")
async def delete_antivirus_default(
    os_name: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Delete antivirus default for a specific OS."""
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    with session_local() as session:
        # Check if user has permission to manage antivirus defaults
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.MANAGE_ANTIVIRUS_DEFAULTS):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: MANAGE_ANTIVIRUS_DEFAULTS role required"),
            )

    try:
        # Get user for audit logging
        session_local_audit = sessionmaker(
            autocommit=False, autoflush=False, bind=db.get_bind()
        )
        with session_local_audit() as session:
            auth_user = (
                session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )

        default = (
            db.query(models.AntivirusDefault)
            .filter(models.AntivirusDefault.os_name == os_name)
            .first()
        )

        if default:
            default_id = str(default.id)
            default_os_name = default.os_name
            db.delete(default)
            db.commit()

            logger.info("Antivirus default deleted for OS: %s", os_name)

            # Log audit entry for deletion
            AuditService.log_delete(
                db=db,
                entity_type=EntityType.SETTING,
                entity_name=f"Antivirus Default for {default_os_name}",
                user_id=auth_user.id,
                username=current_user,
                entity_id=default_id,
                details={"os_name": default_os_name},
            )

            return {"message": _("Antivirus default deleted successfully")}

        return {"message": _("No antivirus default found for this OS")}

    except Exception as e:
        logger.error("Error deleting antivirus default for OS %s: %s", os_name, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete antivirus default: %s") % str(e),
        ) from e
