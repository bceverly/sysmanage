"""
API routes for CVE database refresh settings management in SysManage.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence import models
from backend.services.audit_service import ActionType, AuditService, EntityType
from backend.vulnerability.cve_refresh_service import (
    CVE_SOURCES,
    CveRefreshError,
    cve_refresh_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Error message constants
ERROR_USER_NOT_FOUND = "User not found"
ERROR_ADMIN_REQUIRED = "Permission denied: Administrator role required"


# Response Models


class CveSourceInfo(BaseModel):
    """Information about a CVE data source."""

    name: str
    description: str
    enabled_by_default: bool


class CveRefreshSettingsResponse(BaseModel):
    """Response model for CVE refresh settings."""

    id: str
    enabled: bool
    refresh_interval_hours: int
    enabled_sources: List[str]
    has_nvd_api_key: bool
    last_refresh_at: Optional[datetime] = None
    next_refresh_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @validator("id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID to string."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class CveRefreshSettingsUpdate(BaseModel):
    """Request model for updating CVE refresh settings."""

    enabled: Optional[bool] = None
    refresh_interval_hours: Optional[int] = None
    enabled_sources: Optional[List[str]] = None
    nvd_api_key: Optional[str] = None

    @validator("refresh_interval_hours")
    def validate_interval(cls, value):  # pylint: disable=no-self-argument
        """Validate refresh interval."""
        if value is not None:
            if value < 1:
                raise ValueError(_("Refresh interval must be at least 1 hour"))
            if value > 168:
                raise ValueError(_("Refresh interval cannot exceed 168 hours (1 week)"))
        return value

    @validator("enabled_sources")
    def validate_sources(cls, value):  # pylint: disable=no-self-argument
        """Validate enabled sources."""
        if value is not None:
            for source in value:
                if source not in CVE_SOURCES:
                    raise ValueError(_("Invalid CVE source: %s") % source)
        return value


class DatabaseStatsResponse(BaseModel):
    """Response model for CVE database statistics."""

    total_cves: int
    total_package_mappings: int
    severity_counts: Dict[str, int]
    last_refresh_at: Optional[datetime] = None
    next_refresh_at: Optional[datetime] = None
    last_successful_ingestion: Optional[Dict[str, Any]] = None


class IngestionLogResponse(BaseModel):
    """Response model for ingestion log entries."""

    id: str
    source: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    vulnerabilities_processed: Optional[int] = None
    packages_processed: Optional[int] = None
    error_message: Optional[str] = None

    @validator("id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID to string."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class RefreshResultResponse(BaseModel):
    """Response model for refresh operation results."""

    started_at: str
    completed_at: Optional[str] = None
    sources: Dict[str, Any]
    total_vulnerabilities: int
    total_packages: int
    errors: List[str]


# API Endpoints


@router.get("/sources", response_model=Dict[str, CveSourceInfo])
async def get_available_sources(dependencies=Depends(JWTBearer())):
    """Get list of available CVE data sources."""
    return {
        source_id: CveSourceInfo(
            name=source_info["name"],
            description=source_info["description"],
            enabled_by_default=source_info["enabled_by_default"],
        )
        for source_id, source_info in CVE_SOURCES.items()
    }


@router.get("/settings", response_model=CveRefreshSettingsResponse)
async def get_cve_refresh_settings(
    db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Get current CVE refresh settings."""
    try:
        settings = cve_refresh_service.get_settings(db)
        return CveRefreshSettingsResponse(
            id=str(settings.id),
            enabled=settings.enabled,
            refresh_interval_hours=settings.refresh_interval_hours,
            enabled_sources=settings.enabled_sources or [],
            has_nvd_api_key=settings.nvd_api_key is not None,
            last_refresh_at=settings.last_refresh_at,
            next_refresh_at=settings.next_refresh_at,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
    except Exception as e:
        logger.error("Error getting CVE refresh settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve CVE refresh settings: %s") % str(e),
        ) from e


@router.put("/settings", response_model=CveRefreshSettingsResponse)
async def update_cve_refresh_settings(
    settings_update: CveRefreshSettingsUpdate,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Update CVE refresh settings."""
    # Check user permissions
    auth_user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not auth_user:
        raise HTTPException(status_code=401, detail=_(ERROR_USER_NOT_FOUND))

    # Require admin role for CVE settings
    if not auth_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=_(ERROR_ADMIN_REQUIRED),
        )

    try:
        settings = cve_refresh_service.update_settings(
            db,
            enabled=settings_update.enabled,
            refresh_interval_hours=settings_update.refresh_interval_hours,
            enabled_sources=settings_update.enabled_sources,
            nvd_api_key=settings_update.nvd_api_key,
        )

        # Log audit entry
        AuditService.log_update(
            db=db,
            entity_type=EntityType.SETTING,
            entity_name="CVE Refresh Settings",
            user_id=auth_user.id,
            username=current_user,
            entity_id=str(settings.id),
            details={
                "enabled": settings.enabled,
                "refresh_interval_hours": settings.refresh_interval_hours,
                "enabled_sources": settings.enabled_sources,
                "has_nvd_api_key": settings.nvd_api_key is not None,
            },
        )

        return CveRefreshSettingsResponse(
            id=str(settings.id),
            enabled=settings.enabled,
            refresh_interval_hours=settings.refresh_interval_hours,
            enabled_sources=settings.enabled_sources or [],
            has_nvd_api_key=settings.nvd_api_key is not None,
            last_refresh_at=settings.last_refresh_at,
            next_refresh_at=settings.next_refresh_at,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error updating CVE refresh settings: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to update CVE refresh settings: %s") % str(e),
        ) from e


@router.get("/stats", response_model=DatabaseStatsResponse)
async def get_database_stats(
    db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Get CVE database statistics."""
    try:
        stats = cve_refresh_service.get_database_stats(db)
        return DatabaseStatsResponse(**stats)
    except Exception as e:
        logger.error("Error getting CVE database stats: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve CVE database statistics: %s") % str(e),
        ) from e


@router.get("/history", response_model=List[IngestionLogResponse])
async def get_ingestion_history(
    limit: int = 10, db: Session = Depends(get_db), dependencies=Depends(JWTBearer())
):
    """Get CVE ingestion history."""
    try:
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=400, detail=_("Limit must be between 1 and 100")
            )

        logs = cve_refresh_service.get_ingestion_history(db, limit)
        return [
            IngestionLogResponse(
                id=str(log.id),
                source=log.source,
                started_at=log.started_at,
                completed_at=log.completed_at,
                status=log.status,
                vulnerabilities_processed=log.vulnerabilities_processed,
                packages_processed=log.packages_processed,
                error_message=log.error_message,
            )
            for log in logs
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting CVE ingestion history: %s", e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve CVE ingestion history: %s") % str(e),
        ) from e


@router.post("/refresh", response_model=RefreshResultResponse)
async def trigger_cve_refresh(
    background_tasks: BackgroundTasks,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """
    Trigger a CVE database refresh.

    If source is specified, only refresh from that source.
    Otherwise, refresh from all enabled sources.
    """
    # Check user permissions - require admin for CVE refresh
    auth_user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not auth_user:
        raise HTTPException(status_code=401, detail=_(ERROR_USER_NOT_FOUND))

    if not auth_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=_(ERROR_ADMIN_REQUIRED),
        )

    if source and source not in CVE_SOURCES:
        raise HTTPException(
            status_code=400, detail=_("Invalid CVE source: %s") % source
        )

    try:
        # Run the refresh (this can take a while)
        if source:
            settings = cve_refresh_service.get_settings(db)
            result = await cve_refresh_service.refresh_from_source(
                db, source, settings.nvd_api_key
            )
            return RefreshResultResponse(
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                sources={source: {"status": "success", **result}},
                total_vulnerabilities=result.get("vulnerabilities_processed", 0),
                total_packages=result.get("packages_processed", 0),
                errors=[],
            )
        else:
            # Refresh each enabled source individually so that one source
            # failure does not prevent the remaining sources from running.
            settings = cve_refresh_service.get_settings(db)
            enabled_sources = settings.enabled_sources or list(CVE_SOURCES.keys())
            started_at = datetime.now().isoformat()

            all_sources: Dict[str, Any] = {}
            all_errors: List[str] = []
            total_vulns = 0
            total_pkgs = 0

            for src in enabled_sources:
                try:
                    src_result = await cve_refresh_service.refresh_from_source(
                        db, src, settings.nvd_api_key
                    )
                    all_sources[src] = {"status": "success", **src_result}
                    total_vulns += src_result.get("vulnerabilities_processed", 0)
                    total_pkgs += src_result.get("packages_processed", 0)
                except Exception as src_e:
                    logger.error("CVE refresh failed for source %s: %s", src, src_e)
                    all_sources[src] = {"status": "error", "error": str(src_e)}
                    all_errors.append(_("Source %s failed: %s") % (src, str(src_e)))

            return RefreshResultResponse(
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
                sources=all_sources,
                total_vulnerabilities=total_vulns,
                total_packages=total_pkgs,
                errors=all_errors,
            )

    except CveRefreshError as e:
        raise HTTPException(
            status_code=500, detail=_("CVE refresh failed: %s") % str(e)
        ) from e
    except Exception as e:
        logger.error("Error triggering CVE refresh: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to trigger CVE refresh: %s") % str(e)
        ) from e


@router.delete("/nvd-api-key")
async def clear_nvd_api_key(
    db: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user=Depends(get_current_user),
):
    """Clear the stored NVD API key."""
    # Check user permissions - require admin
    auth_user = db.query(models.User).filter(models.User.userid == current_user).first()
    if not auth_user:
        raise HTTPException(status_code=401, detail=_(ERROR_USER_NOT_FOUND))

    if not auth_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=_(ERROR_ADMIN_REQUIRED),
        )

    try:
        settings = cve_refresh_service.get_settings(db)
        settings.nvd_api_key = None
        db.commit()

        # Log audit entry
        AuditService.log_delete(
            db=db,
            entity_type=EntityType.SETTING,
            entity_name="NVD API Key",
            user_id=auth_user.id,
            username=current_user,
            entity_id=str(settings.id),
        )

        return {"message": _("NVD API key cleared successfully")}

    except Exception as e:
        # Log error without exception details to avoid potential credential leakage
        logger.error("Error clearing NVD API key", exc_info=True)
        raise HTTPException(
            status_code=500, detail=_("Failed to clear NVD API key")
        ) from e
