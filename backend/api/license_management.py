"""
Pro+ License Management API endpoints.

Provides API access to Pro+ license information and installation.
Health analysis and vulnerability scanning routes are provided by
the respective Cython modules via proplus_routes.py.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.licensing.license_service import license_service
from backend.persistence import db as db_module
from backend.persistence import models
from backend.persistence.db import get_db
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.api.license_management")

router = APIRouter()


# =============================================================================
# LICENSE MANAGEMENT SCHEMAS
# =============================================================================


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


# =============================================================================
# LICENSE ENDPOINTS
# =============================================================================


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


# =============================================================================
# MODULE COMPATIBILITY (UI BANNER FALLBACK)
# =============================================================================


class ModuleCompatibilityEntry(BaseModel):
    """One Pro+ module that failed the migration-compatibility check."""

    module_code: str
    required_revision: str
    required_revision_human: Optional[str] = None
    current_revision: Optional[str] = None


class ModuleCompatibilityResponse(BaseModel):
    """List of Pro+ modules that need a database migration before they will load."""

    incompatibilities: List[ModuleCompatibilityEntry]


@router.get("/license/module-compat", response_model=ModuleCompatibilityResponse)
async def get_module_compatibility(
    current_user: str = Depends(get_current_user),
):
    """
    Return any Pro+ modules whose declared minimum OSS alembic revision is
    above the current ``alembic_version`` row.

    The UI displays a banner when this list is non-empty, instructing the
    operator to run ``alembic upgrade head``.  This is a fallback safety
    net — the normal path is for migrations to be run as part of the
    upgrade procedure.
    """
    # pylint: disable=import-outside-toplevel
    from backend.licensing.migration_compat import get_incompatibilities

    del current_user  # auth-only check; no per-user filtering

    entries = [
        ModuleCompatibilityEntry(
            module_code=item.module_code,
            required_revision=item.required_revision,
            required_revision_human=item.required_revision_human,
            current_revision=item.current_revision,
        )
        for item in get_incompatibilities()
    ]
    return ModuleCompatibilityResponse(incompatibilities=entries)
