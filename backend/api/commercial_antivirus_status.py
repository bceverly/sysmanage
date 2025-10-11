"""
This module houses the API routes for commercial antivirus status management in SysManage.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class CommercialAntivirusStatusResponse(BaseModel):
    """Response model for commercial antivirus status."""

    id: str
    host_id: str
    product_name: Optional[str] = None
    product_version: Optional[str] = None
    service_enabled: Optional[bool] = None
    antispyware_enabled: Optional[bool] = None
    antivirus_enabled: Optional[bool] = None
    realtime_protection_enabled: Optional[bool] = None
    full_scan_age: Optional[int] = None
    quick_scan_age: Optional[int] = None
    full_scan_end_time: Optional[datetime] = None
    quick_scan_end_time: Optional[datetime] = None
    signature_last_updated: Optional[datetime] = None
    signature_version: Optional[str] = None
    tamper_protection_enabled: Optional[bool] = None
    created_at: datetime
    last_updated: datetime

    @validator("id", "host_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


@router.get(
    "/hosts/{host_id}/commercial-antivirus-status",
    response_model=Optional[CommercialAntivirusStatusResponse],
)
async def get_commercial_antivirus_status(
    host_id: str,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
):
    """Get commercial antivirus status for a specific host."""
    try:
        # Convert host_id to UUID
        try:
            host_uuid = uuid.UUID(host_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid host ID format"),
            ) from e

        # Check if host exists
        host = db.query(models.Host).filter(models.Host.id == host_uuid).first()
        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found"),
            )

        # Get commercial antivirus status
        status = (
            db.query(models.CommercialAntivirusStatus)
            .filter(models.CommercialAntivirusStatus.host_id == host_uuid)
            .first()
        )

        if not status:
            return None

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting commercial antivirus status for host %s: %s", host_id, e
        )
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve commercial antivirus status: %s") % str(e),
        ) from e
