"""
API routes for package management in SysManage.
Provides endpoints for retrieving available packages from different package managers.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import count

from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import AvailablePackage

# Authenticated router for package management
router = APIRouter(dependencies=[Depends(JWTBearer())])


class PackageInfo(BaseModel):
    """Package information model for API responses."""

    name: str
    version: str
    description: Optional[str] = None
    package_manager: str


class PackageManagerSummary(BaseModel):
    """Summary of packages per package manager."""

    package_manager: str
    package_count: int


class OSPackageSummary(BaseModel):
    """Summary of packages per OS/version combination."""

    os_name: str
    os_version: str
    package_managers: List[PackageManagerSummary]
    total_packages: int


@router.get("/summary", response_model=List[OSPackageSummary])
async def get_packages_summary(db: Session = Depends(get_db)):
    """
    Get a summary of available packages grouped by OS and package manager.

    Returns package counts for each OS/version/package manager combination.
    """
    try:
        # Query to get package counts grouped by OS, version, and package manager
        results = (
            db.query(
                AvailablePackage.os_name,
                AvailablePackage.os_version,
                AvailablePackage.package_manager,
                count(AvailablePackage.id).label("package_count"),
            )
            .group_by(
                AvailablePackage.os_name,
                AvailablePackage.os_version,
                AvailablePackage.package_manager,
            )
            .all()
        )

        # Organize results by OS/version
        os_summary = {}
        for result in results:
            os_key = f"{result.os_name}:{result.os_version}"

            if os_key not in os_summary:
                os_summary[os_key] = {
                    "os_name": result.os_name,
                    "os_version": result.os_version,
                    "package_managers": [],
                    "total_packages": 0,
                }

            manager_summary = PackageManagerSummary(
                package_manager=result.package_manager,
                package_count=result.package_count,
            )

            os_summary[os_key]["package_managers"].append(manager_summary)
            os_summary[os_key]["total_packages"] += result.package_count

        # Convert to list format
        summary_list = [OSPackageSummary(**summary) for summary in os_summary.values()]

        # Sort by OS name, then version
        summary_list.sort(key=lambda x: (x.os_name, x.os_version))

        return summary_list

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to retrieve package summary: %s") % str(e)
        ) from e


@router.get("/managers", response_model=List[str])
async def get_package_managers(
    os_name: Optional[str] = Query(None, description="Filter by OS name"),
    os_version: Optional[str] = Query(None, description="Filter by OS version"),
    db: Session = Depends(get_db),
):
    """
    Get list of available package managers.

    Optionally filter by OS name and version.
    """
    try:
        query = db.query(distinct(AvailablePackage.package_manager))

        if os_name:
            query = query.filter(AvailablePackage.os_name == os_name)

        if os_version:
            query = query.filter(AvailablePackage.os_version == os_version)

        managers = [result[0] for result in query.all()]
        return sorted(managers)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve package managers: %s") % str(e),
        ) from e


@router.get("/search", response_model=List[PackageInfo])
async def search_packages(
    *,
    query: str = Query(..., min_length=1, description="Search term for package name"),
    os_name: Optional[str] = Query(None, description="Filter by OS name"),
    os_version: Optional[str] = Query(None, description="Filter by OS version"),
    package_manager: Optional[str] = Query(
        None, description="Filter by package manager"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
):
    """
    Search for packages by name.

    Supports filtering by OS, version, and package manager.
    Results are paginated with limit and offset.
    """
    try:
        db_query = db.query(AvailablePackage).filter(
            AvailablePackage.package_name.ilike(f"%{query}%")
        )

        if os_name:
            db_query = db_query.filter(AvailablePackage.os_name == os_name)

        if os_version:
            db_query = db_query.filter(AvailablePackage.os_version == os_version)

        if package_manager:
            db_query = db_query.filter(
                AvailablePackage.package_manager == package_manager
            )

        # Apply pagination
        packages = (
            db_query.order_by(
                AvailablePackage.package_name, AvailablePackage.package_manager
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            PackageInfo(
                name=pkg.package_name,
                version=pkg.package_version,
                description=pkg.package_description,
                package_manager=pkg.package_manager,
            )
            for pkg in packages
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to search packages: %s") % str(e)
        ) from e


@router.get("/os-versions", response_model=List[dict])
async def get_os_versions(db: Session = Depends(get_db)):
    """
    Get list of available OS name/version combinations.

    Returns list of dictionaries with os_name and os_version fields.
    """
    try:
        # Get unique OS/version combinations
        os_versions = (
            db.query(AvailablePackage.os_name, AvailablePackage.os_version)
            .distinct()
            .all()
        )

        return [
            {"os_name": result.os_name, "os_version": result.os_version}
            for result in os_versions
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to retrieve OS versions: %s") % str(e)
        ) from e


@router.get("/by-manager/{manager_name}", response_model=List[PackageInfo])
async def get_packages_by_manager(
    manager_name: str,
    *,
    os_name: Optional[str] = Query(None, description="Filter by OS name"),
    os_version: Optional[str] = Query(None, description="Filter by OS version"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
):
    """
    Get packages for a specific package manager.

    Supports filtering by OS and version with pagination.
    """
    try:
        db_query = db.query(AvailablePackage).filter(
            AvailablePackage.package_manager == manager_name
        )

        if os_name:
            db_query = db_query.filter(AvailablePackage.os_name == os_name)

        if os_version:
            db_query = db_query.filter(AvailablePackage.os_version == os_version)

        packages = (
            db_query.order_by(AvailablePackage.package_name)
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            PackageInfo(
                name=pkg.package_name,
                version=pkg.package_version,
                description=pkg.package_description,
                package_manager=pkg.package_manager,
            )
            for pkg in packages
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve packages for manager %s: %s")
            % (manager_name, str(e)),
        ) from e
