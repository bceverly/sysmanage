"""
This module houses the API routes for user preferences management in SysManage.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class DataGridColumnPreferenceRequest(BaseModel):
    """Request model for updating DataGrid column preferences."""

    grid_identifier: str
    hidden_columns: List[str]

    @validator("grid_identifier")
    def validate_grid_identifier(
        cls, grid_identifier
    ):  # pylint: disable=no-self-argument
        """Validate grid identifier."""
        if not grid_identifier or grid_identifier.strip() == "":
            raise ValueError(_("Grid identifier is required"))
        if len(grid_identifier) > 255:
            raise ValueError(_("Grid identifier must be 255 characters or less"))
        return grid_identifier.strip()


class DataGridColumnPreferenceResponse(BaseModel):
    """Response model for DataGrid column preferences."""

    id: str
    user_id: str
    grid_identifier: str
    hidden_columns: List[str]
    created_at: datetime
    updated_at: datetime

    @validator("id", "user_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


@router.get(
    "/column-preferences/{grid_identifier}",
    response_model=Optional[DataGridColumnPreferenceResponse],
)
async def get_column_preferences(
    grid_identifier: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Get column preferences for a specific grid."""
    try:
        # Get user
        user = db.query(models.User).filter(models.User.userid == current_user).first()
        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Get preferences
        preference = (
            db.query(models.UserDataGridColumnPreference)
            .filter(
                models.UserDataGridColumnPreference.user_id == user.id,
                models.UserDataGridColumnPreference.grid_identifier == grid_identifier,
            )
            .first()
        )

        if not preference:
            return None

        return DataGridColumnPreferenceResponse(
            id=str(preference.id),
            user_id=str(preference.user_id),
            grid_identifier=preference.grid_identifier,
            hidden_columns=preference.hidden_columns,
            created_at=preference.created_at,
            updated_at=preference.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting column preferences: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve column preferences: %s") % str(e),
        ) from e


@router.put("/column-preferences", response_model=DataGridColumnPreferenceResponse)
async def update_column_preferences(
    preference_request: DataGridColumnPreferenceRequest,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Update column preferences for a specific grid."""
    try:
        # Get user
        user = db.query(models.User).filter(models.User.userid == current_user).first()
        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Check if preference already exists
        preference = (
            db.query(models.UserDataGridColumnPreference)
            .filter(
                models.UserDataGridColumnPreference.user_id == user.id,
                models.UserDataGridColumnPreference.grid_identifier
                == preference_request.grid_identifier,
            )
            .first()
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if preference:
            # Update existing preference
            preference.hidden_columns = preference_request.hidden_columns
            preference.updated_at = now
        else:
            # Create new preference
            preference = models.UserDataGridColumnPreference(
                user_id=user.id,
                grid_identifier=preference_request.grid_identifier,
                hidden_columns=preference_request.hidden_columns,
                created_at=now,
                updated_at=now,
            )
            db.add(preference)

        db.commit()
        db.refresh(preference)

        logger.info(
            "Column preferences updated for user %s, grid %s",
            current_user,
            preference_request.grid_identifier,
        )

        return DataGridColumnPreferenceResponse(
            id=str(preference.id),
            user_id=str(preference.user_id),
            grid_identifier=preference.grid_identifier,
            hidden_columns=preference_request.hidden_columns,
            created_at=preference.created_at,
            updated_at=preference.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating column preferences: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to update column preferences: %s") % str(e),
        ) from e


@router.delete("/column-preferences/{grid_identifier}")
async def delete_column_preferences(
    grid_identifier: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Delete column preferences for a specific grid (reset to defaults)."""
    try:
        # Get user
        user = db.query(models.User).filter(models.User.userid == current_user).first()
        if not user:
            raise HTTPException(status_code=404, detail=_("User not found"))

        # Delete preference
        preference = (
            db.query(models.UserDataGridColumnPreference)
            .filter(
                models.UserDataGridColumnPreference.user_id == user.id,
                models.UserDataGridColumnPreference.grid_identifier == grid_identifier,
            )
            .first()
        )

        if preference:
            db.delete(preference)
            db.commit()
            logger.info(
                "Column preferences deleted for user %s, grid %s",
                current_user,
                grid_identifier,
            )
            return {"message": _("Column preferences reset to defaults")}

        return {"message": _("No preferences found to delete")}

    except Exception as e:
        logger.error("Error deleting column preferences: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete column preferences: %s") % str(e),
        ) from e
