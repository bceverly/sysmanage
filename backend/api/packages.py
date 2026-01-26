"""
API routes for package management in SysManage.
Provides endpoints for retrieving available packages from different package managers.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct
from sqlalchemy.orm import Session

from backend.api.error_constants import FILTER_BY_OS_NAME, FILTER_BY_OS_VERSION
from backend.api.package_host_selector import find_hosts_for_os, select_best_host
from backend.api.packages_helpers import (
    get_packages_summary_sync,
    search_packages_count_sync,
    search_packages_sync,
)
from backend.api.packages_models import (
    InstallationCompletionRequest,
    InstallationHistoryItem,
    InstallationHistoryResponse,
    OSPackageSummary,
    PackageInfo,
    PackageInstallRequest,
    PackageInstallResponse,
    PackageUninstallRequest,
    PackageUninstallResponse,
)
from backend.api.packages_operations import (
    install_packages_operation,
    uninstall_packages_operation,
)
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import (
    AvailablePackage,
    Host,
    InstallationPackage,
    InstallationRequest,
)
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

# Authenticated router for package management
router = APIRouter(dependencies=[Depends(JWTBearer())])


@router.get("/summary", response_model=List[OSPackageSummary])
async def get_packages_summary():
    """
    Get a summary of available packages grouped by OS and package manager.
    Runs the database query in a thread pool to avoid blocking the event loop.

    Returns package counts for each OS/version/package manager combination.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    summary_dicts = await loop.run_in_executor(None, get_packages_summary_sync)
    return [OSPackageSummary(**summary) for summary in summary_dicts]


@router.get("/managers", response_model=List[str])
async def get_package_managers(
    os_name: Optional[str] = Query(None, description=FILTER_BY_OS_NAME),
    os_version: Optional[str] = Query(None, description=FILTER_BY_OS_VERSION),
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


@router.get("/search/count", response_model=dict)
async def search_packages_count(
    *,
    query: str = Query(..., min_length=1, description="Search term for package name"),
    os_name: Optional[str] = Query(None, description=FILTER_BY_OS_NAME),
    os_version: Optional[str] = Query(None, description=FILTER_BY_OS_VERSION),
    package_manager: Optional[str] = Query(
        None, description="Filter by package manager"
    ),
):
    """
    Get count of packages matching search criteria.
    Runs the database query in a thread pool to avoid blocking the event loop.

    This endpoint returns only the count of matching packages for pagination.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, search_packages_count_sync, query, os_name, os_version, package_manager
    )


@router.get("/search", response_model=List[PackageInfo])
async def search_packages(
    *,
    query: str = Query(..., min_length=1, description="Search term for package name"),
    os_name: Optional[str] = Query(None, description=FILTER_BY_OS_NAME),
    os_version: Optional[str] = Query(None, description=FILTER_BY_OS_VERSION),
    package_manager: Optional[str] = Query(
        None, description="Filter by package manager"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    Search for packages by name.
    Runs the database query in a thread pool to avoid blocking the event loop.

    Supports filtering by OS, version, and package manager.
    Results are paginated with limit and offset.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    package_dicts = await loop.run_in_executor(
        None,
        search_packages_sync,
        query,
        os_name,
        os_version,
        package_manager,
        limit,
        offset,
    )
    return [PackageInfo(**pkg) for pkg in package_dicts]


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
    os_name: Optional[str] = Query(None, description=FILTER_BY_OS_NAME),
    os_version: Optional[str] = Query(None, description=FILTER_BY_OS_VERSION),
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


@router.post("/refresh/{os_name}/{os_version:path}")
async def refresh_packages_for_os_version(
    os_name: str, os_version: str, db: Session = Depends(get_db)
):
    """
    Trigger package collection refresh for a specific OS/version combination.

    Finds a random online host with the specified OS/version and requests
    it to collect and transmit updated package information.
    """
    try:
        # Find hosts matching the OS and version
        hosts = find_hosts_for_os(db, os_name, os_version)

        if not hosts:
            raise HTTPException(
                status_code=404,
                detail=_("No active hosts found for %s %s") % (os_name, os_version),
            )

        # Select best host with bias towards those with more package managers
        selected_host = select_best_host(hosts)

        # Create command message to collect packages
        command_message = create_command_message(
            command_type="collect_available_packages", parameters={}
        )

        # Queue the command to the selected host
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=command_message,
            direction=QueueDirection.OUTBOUND,
            host_id=selected_host.id,
            priority=Priority.NORMAL,
            db=db,
        )

        return {
            "success": True,
            "message": _("Package collection requested from host %s")
            % selected_host.fqdn,
            "host_id": selected_host.id,
            "host_fqdn": selected_host.fqdn,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to request package refresh: %s") % str(e)
        ) from e


@router.post("/install/{host_id}", response_model=PackageInstallResponse)
async def install_packages(
    host_id: str,
    request: PackageInstallRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Queue package installation for a specific host using UUID-based grouping.

    Creates a single installation request with multiple packages grouped under one UUID.
    The agent will receive this UUID and return it when reporting completion.
    """
    return await install_packages_operation(host_id, request, db, current_user)


@router.post("/uninstall/{host_id}", response_model=PackageUninstallResponse)
async def uninstall_packages(
    host_id: str,
    request: PackageUninstallRequest,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Queue package uninstallation for a specific host using UUID-based grouping.

    Creates a single uninstallation request with multiple packages grouped under one UUID.
    The agent will receive this UUID and return it when reporting completion.
    """
    return await uninstall_packages_operation(host_id, request, db, current_user)


@router.get(
    "/installation-history/{host_id}", response_model=InstallationHistoryResponse
)
async def get_installation_history(
    host_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> InstallationHistoryResponse:
    """
    Get installation history for a specific host using UUID-based grouping.

    Args:
        host_id: ID of the host to get installation history for
        db: Database session
        limit: Maximum number of records to return (1-100)
        offset: Number of records to skip for pagination

    Returns:
        InstallationHistoryResponse with list of installation requests (each containing multiple packages)
    """
    try:
        # Verify host exists
        host = db.query(Host).filter(Host.id == host_id).first()
        if not host:
            raise HTTPException(status_code=404, detail=_("Host not found"))

        # Get total count of installation requests for this host
        total_count = (
            db.query(InstallationRequest)
            .filter(InstallationRequest.host_id == host_id)
            .count()
        )

        # Get installation requests with pagination, ordered by most recent first
        installation_requests = (
            db.query(InstallationRequest)
            .filter(InstallationRequest.host_id == host_id)
            .order_by(InstallationRequest.requested_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Convert to response format, creating comma-separated package names
        installation_items = []
        for request in installation_requests:
            # Create comma-separated list of package names
            package_names = ", ".join([pkg.package_name for pkg in request.packages])

            installation_items.append(
                InstallationHistoryItem(
                    request_id=str(request.id),
                    requested_by=request.requested_by,
                    status=request.status,
                    operation_type=request.operation_type,
                    requested_at=request.requested_at,
                    completed_at=request.completed_at,
                    installation_log=request.result_log,
                    package_names=package_names,
                )
            )

        return InstallationHistoryResponse(
            installations=installation_items,
            total_count=total_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve installation history: %s") % str(e),
        ) from e


@router.post("/installation-complete")
async def handle_installation_completion(
    request: InstallationCompletionRequest,
    db: Session = Depends(get_db),
):
    """
    Handle completion notification from agent.

    This endpoint is called by the agent when a package installation request completes.
    The agent passes back the request_id (UUID) and the result log.
    """
    try:
        # Find the installation request
        installation_request = (
            db.query(InstallationRequest)
            .filter(InstallationRequest.id == request.request_id)
            .first()
        )

        if not installation_request:
            raise HTTPException(
                status_code=404,
                detail=_("Installation request not found: %s") % request.request_id,
            )

        # Update the request with completion data
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        installation_request.completed_at = now
        installation_request.status = "completed" if request.success else "failed"
        installation_request.result_log = request.result_log
        installation_request.updated_at = now

        db.commit()

        return {"success": True, "message": _("Installation completion recorded")}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to record installation completion: %s") % str(e),
        ) from e


@router.delete("/installation-history/{request_id}")
async def delete_installation_record(
    request_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete an installation record and all its associated packages.
    Args:
        request_id: UUID of the installation request to delete
        db: Database session
    Returns:
        Success message
    """
    try:
        # Find the installation request
        installation_request = (
            db.query(InstallationRequest)
            .filter(InstallationRequest.id == request_id)
            .first()
        )

        if not installation_request:
            raise HTTPException(
                status_code=404, detail=_("Installation record not found")
            )

        # Delete associated packages first (due to foreign key constraint)
        db.query(InstallationPackage).filter(
            InstallationPackage.installation_request_id == request_id
        ).delete()

        # Delete the installation request
        db.delete(installation_request)
        db.commit()

        return {
            "success": True,
            "message": _("Installation record deleted successfully"),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to delete installation record: %s") % str(e),
        ) from e
