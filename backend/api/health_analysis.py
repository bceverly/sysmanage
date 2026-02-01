"""
Pro+ Health Analysis API endpoints.

Provides API access to AI-powered health analysis for hosts.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.health.health_service import HealthAnalysisError, health_service
from backend.i18n import _
from backend.licensing.feature_gate import requires_feature, requires_module
from backend.licensing.features import FeatureCode, ModuleCode
from backend.licensing.license_service import license_service
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.health_analysis")

router = APIRouter()

# Error message constants
ERROR_HOST_NOT_FOUND = "Host not found"


# Pydantic schemas
class IssueResponse(BaseModel):
    """Schema for a health issue."""

    severity: str = Field(..., description="Issue severity: critical, warning, info")
    category: str = Field(..., description="Issue category")
    message: str = Field(..., description="Human-readable issue description")
    details: Optional[dict] = Field(None, description="Additional issue details")


class RecommendationResponse(BaseModel):
    """Schema for a health recommendation."""

    priority: str = Field(..., description="Priority: high, medium, low")
    category: str = Field(..., description="Recommendation category")
    message: str = Field(..., description="Human-readable recommendation")
    action: Optional[str] = Field(None, description="Suggested action to take")


class HealthAnalysisResponse(BaseModel):
    """Schema for health analysis response."""

    id: str
    host_id: str
    analyzed_at: str
    score: int = Field(..., ge=0, le=100, description="Health score from 0 to 100")
    grade: str = Field(..., description="Letter grade: A+, A, B, C, D, F")
    issues: Optional[List[dict]] = Field(None, description="List of identified issues")
    recommendations: Optional[List[dict]] = Field(
        None, description="List of recommendations"
    )
    analysis_version: Optional[str] = Field(
        None, description="Version of health engine used"
    )

    class Config:
        from_attributes = True


class HealthHistoryResponse(BaseModel):
    """Schema for health analysis history response."""

    analyses: List[HealthAnalysisResponse]
    total: int


class LicenseInfoResponse(BaseModel):
    """Schema for license information response."""

    active: bool
    tier: Optional[str] = None
    license_id: Optional[str] = None
    features: Optional[List[str]] = None
    modules: Optional[List[str]] = None
    expires_at: Optional[str] = None
    customer_name: Optional[str] = None
    parent_hosts: Optional[int] = None
    child_hosts: Optional[int] = None


class LicenseInstallRequest(BaseModel):
    """Schema for license installation request."""

    license_key: str = Field(..., description="The Pro+ license key to install")


class LicenseInstallResponse(BaseModel):
    """Schema for license installation response."""

    success: bool
    message: str
    license_info: Optional[LicenseInfoResponse] = None


# License endpoints
@router.get("/license", response_model=LicenseInfoResponse)
async def get_license_info(current_user: str = Depends(get_current_user)):
    """
    Get current Pro+ license information.

    Returns license details if Pro+ is active, or indicates Community Edition.
    """
    if not license_service.is_pro_plus_active:
        return LicenseInfoResponse(active=False)

    info = license_service.get_license_info()
    return LicenseInfoResponse(
        active=True,
        tier=info.get("tier"),
        license_id=info.get("license_id"),
        features=info.get("features"),
        modules=info.get("modules"),
        expires_at=info.get("expires_at"),
        customer_name=info.get("customer_name"),
        parent_hosts=info.get("parent_hosts"),
        child_hosts=info.get("child_hosts"),
    )


@router.post("/license", response_model=LicenseInstallResponse)
async def install_license(
    request: LicenseInstallRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Install a new Pro+ license key.

    Requires admin privileges.
    """
    # Check if user is admin
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_module.get_engine()
    )
    with session_local() as session:
        user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not user:
            raise HTTPException(status_code=401, detail=_("User not found"))

        if not user.is_admin:
            raise HTTPException(
                status_code=403,
                detail=_("Administrator privileges required to install license"),
            )

    # Install the license
    try:
        result = await license_service.install_license(request.license_key)
    except Exception as e:
        logger.error("License installation error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("License installation failed: %(error)s") % {"error": str(e)},
        ) from e

    if not result.valid:
        return LicenseInstallResponse(
            success=False,
            message=result.error or _("License validation failed"),
        )

    info = license_service.get_license_info()
    return LicenseInstallResponse(
        success=True,
        message=_("License installed successfully"),
        license_info=LicenseInfoResponse(
            active=True,
            tier=info.get("tier"),
            license_id=info.get("license_id"),
            features=info.get("features"),
            modules=info.get("modules"),
            expires_at=info.get("expires_at"),
            customer_name=info.get("customer_name"),
            parent_hosts=info.get("parent_hosts"),
            child_hosts=info.get("child_hosts"),
        ),
    )


# Health analysis endpoints
@router.get("/host/{host_id}/health-analysis", response_model=HealthAnalysisResponse)
@requires_feature(FeatureCode.HEALTH_ANALYSIS)
async def get_host_health_analysis(
    host_id: str,
    refresh: bool = False,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get AI-powered health analysis for a host.

    Requires Pro+ license with health_analysis feature.

    Args:
        host_id: The host ID to analyze
        refresh: If True, run a new analysis instead of returning cached results

    Returns:
        Health analysis with score, grade, issues, and recommendations
    """
    # Import module_loader here to check module availability
    from backend.licensing.module_loader import module_loader

    # Verify host exists
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_(ERROR_HOST_NOT_FOUND),
        )

    try:
        if refresh:
            # Run new analysis - requires module to be loaded
            if not module_loader.is_module_loaded("health_engine"):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "module_not_available",
                        "message": _(
                            "The health analysis module is not currently available. Please try again later."
                        ),
                        "module": "health_engine",
                    },
                )
            result = health_service.analyze_host(host_id)
        else:
            # Get cached result first
            result = health_service.get_latest_analysis(host_id)
            if result is None:
                # No cached result - need to run analysis
                if not module_loader.is_module_loaded("health_engine"):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "error": "module_not_available",
                            "message": _(
                                "The health analysis module is not currently available. No cached analysis exists for this host."
                            ),
                            "module": "health_engine",
                        },
                    )
                result = health_service.analyze_host(host_id)

        return HealthAnalysisResponse(**result)

    except HealthAnalysisError as e:
        logger.error("Health analysis failed for host %s: %s", host_id, e)
        # Check if it's a module loading issue
        error_msg = str(e)
        if "not loaded" in error_msg or "not available" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "module_not_available",
                    "message": error_msg,
                    "module": "health_engine",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post("/host/{host_id}/health-analysis", response_model=HealthAnalysisResponse)
@requires_module(ModuleCode.HEALTH_ENGINE)
async def run_host_health_analysis(
    host_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Run a new health analysis for a host.

    Requires Pro+ license with health_engine module.

    Args:
        host_id: The host ID to analyze

    Returns:
        New health analysis results
    """
    # Verify host exists
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_(ERROR_HOST_NOT_FOUND),
        )

    try:
        result = health_service.analyze_host(host_id)
        return HealthAnalysisResponse(**result)

    except HealthAnalysisError as e:
        logger.error("Health analysis failed for host %s: %s", host_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get(
    "/host/{host_id}/health-analysis/history", response_model=HealthHistoryResponse
)
@requires_feature(FeatureCode.HEALTH_HISTORY)
async def get_host_health_history(
    host_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Get health analysis history for a host.

    Requires Pro+ license with health_history feature.

    Args:
        host_id: The host ID
        limit: Maximum number of records to return (default 10, max 100)

    Returns:
        List of historical health analyses
    """
    # Verify host exists
    host = db.query(models.Host).filter(models.Host.id == host_id).first()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_(ERROR_HOST_NOT_FOUND),
        )

    # Clamp limit
    limit = min(max(1, limit), 100)

    try:
        analyses = health_service.get_analysis_history(host_id, limit)
        return HealthHistoryResponse(
            analyses=[HealthAnalysisResponse(**a) for a in analyses],
            total=len(analyses),
        )

    except Exception as e:
        logger.error("Failed to get health history for host %s: %s", host_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_("Failed to retrieve health history"),
        ) from e
