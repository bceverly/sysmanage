"""
API routes for package management in SysManage.
Provides endpoints for retrieving available packages from different package managers.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.functions import count

from backend.api.package_host_selector import find_hosts_for_os, select_best_host
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.persistence import db as db_module, models
from backend.persistence.db import get_db
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.persistence.models import (
    AvailablePackage,
    Host,
    InstallationPackage,
    InstallationRequest,
)
from backend.security.roles import SecurityRoles
from backend.websocket.messages import create_command_message
from backend.websocket.queue_manager import (
    Priority,
    QueueDirection,
    server_queue_manager,
)

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


class PackageInstallRequest(BaseModel):
    """Request model for package installation."""

    package_names: List[str]
    requested_by: str


class PackageInstallResponse(BaseModel):
    """Response model for package installation."""

    success: bool
    message: str
    request_id: str  # The UUID that groups all packages in this request


class PackageUninstallRequest(BaseModel):
    """Request model for package uninstallation."""

    package_names: List[str]
    requested_by: str


class PackageUninstallResponse(BaseModel):
    """Response model for package uninstallation."""

    success: bool
    message: str
    request_id: str  # The UUID that groups all packages in this request


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


@router.get("/search/count", response_model=dict)
async def search_packages_count(
    *,
    query: str = Query(..., min_length=1, description="Search term for package name"),
    os_name: Optional[str] = Query(None, description="Filter by OS name"),
    os_version: Optional[str] = Query(None, description="Filter by OS version"),
    package_manager: Optional[str] = Query(
        None, description="Filter by package manager"
    ),
    db: Session = Depends(get_db),
):
    """
    Get count of packages matching search criteria.

    This endpoint returns only the count of matching packages for pagination.
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

        total_count = db_query.count()
        return {"total_count": total_count}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to count packages: %s") % str(e)
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
    try:
        # Check if user has permission to add packages
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

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.ADD_PACKAGE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: ADD_PACKAGE role required"),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Validate that packages are not empty
        if not request.package_names:
            raise HTTPException(
                status_code=400,
                detail=_("No packages specified for installation"),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Generate a single UUID for this entire installation request
        request_id = str(uuid.uuid4())

        # Create the primary installation request record
        installation_request = InstallationRequest(
            id=request_id,
            host_id=host_id,
            requested_by=request.requested_by,
            requested_at=now,
            status="pending",
            operation_type="install",
            created_at=now,
            updated_at=now,
        )
        db.add(installation_request)

        # Create package records for each package in the request
        for package_name in request.package_names:
            package_record = InstallationPackage(
                installation_request_id=request_id,
                package_name=package_name,
                package_manager="auto",  # Let the agent determine the best package manager
            )
            db.add(package_record)

        # Commit the installation records first
        db.commit()

        # Create a single message for the entire package installation request
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "install_packages",  # New command type for multiple packages
                "parameters": {
                    "request_id": request_id,  # The UUID that groups everything
                    "packages": [
                        {"package_name": pkg_name, "package_manager": "auto"}
                        for pkg_name in request.package_names
                    ],
                    "requested_by": request.requested_by,
                    "requested_at": now.isoformat(),
                },
            },
        }

        # Queue the single message using the server queue manager
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Update request status to in_progress
        installation_request.status = "in_progress"
        installation_request.updated_at = now

        # Final commit for status updates
        db.commit()

        # Audit log the package installation request
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.PACKAGE,
            description=_("Queued installation of %d packages on host %s")
            % (len(request.package_names), host.fqdn),
            result=Result.SUCCESS,
            user_id=user.id,
            username=current_user,
            entity_id=host_id,
            entity_name=host.fqdn,
            details={
                "request_id": request_id,
                "packages": request.package_names,
                "requested_by": request.requested_by,
            },
        )

        return PackageInstallResponse(
            success=True,
            message=_("Successfully queued %d packages for installation")
            % len(request.package_names),
            request_id=request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue package installation: %s") % str(e),
        ) from e


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
    try:
        # Check if user has permission to remove packages
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

            if user._role_cache is None:
                user.load_role_cache(session)

            if not user.has_role(SecurityRoles.REMOVE_PACKAGE):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: REMOVE_PACKAGE role required"),
                )

        # Validate host exists and is active
        host = (
            db.query(Host)
            .filter(
                Host.id == host_id,
                Host.active.is_(True),
                Host.approval_status == "approved",
            )
            .first()
        )

        if not host:
            raise HTTPException(
                status_code=404,
                detail=_("Host not found or not active"),
            )

        # Validate that packages are not empty
        if not request.package_names:
            raise HTTPException(
                status_code=400,
                detail=_("No packages specified for uninstallation"),
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Generate a single UUID for this entire uninstallation request
        request_id = str(uuid.uuid4())

        # Create the primary uninstallation request record
        installation_request = InstallationRequest(
            id=request_id,
            host_id=host_id,
            requested_by=request.requested_by,
            requested_at=now,
            status="pending",
            operation_type="uninstall",
            created_at=now,
            updated_at=now,
        )
        db.add(installation_request)

        # Create package records for each package in the request
        for package_name in request.package_names:
            package_record = InstallationPackage(
                installation_request_id=request_id,
                package_name=package_name,
                package_manager="auto",  # Let the agent determine the best package manager
            )
            db.add(package_record)

        # Commit the uninstallation records first
        db.commit()

        # Create a single message for the entire package uninstallation request
        message_data = {
            "command_type": "generic_command",
            "parameters": {
                "command_type": "uninstall_packages",  # New command type for multiple package uninstallation
                "parameters": {
                    "request_id": request_id,  # The UUID that groups everything
                    "packages": [
                        {"package_name": pkg_name, "package_manager": "auto"}
                        for pkg_name in request.package_names
                    ],
                    "requested_by": request.requested_by,
                    "requested_at": now.isoformat(),
                },
            },
        }

        # Queue the single message using the server queue manager
        server_queue_manager.enqueue_message(
            message_type="command",
            message_data=message_data,
            direction=QueueDirection.OUTBOUND,
            host_id=host_id,
            priority=Priority.NORMAL,
            db=db,
        )

        # Update request status to in_progress
        installation_request.status = "in_progress"
        installation_request.updated_at = now

        # Final commit for status updates
        db.commit()

        # Audit log the package uninstallation request
        AuditService.log(
            db=db,
            action_type=ActionType.UPDATE,
            entity_type=EntityType.PACKAGE,
            description=_("Queued uninstallation of %d packages on host %s")
            % (len(request.package_names), host.fqdn),
            result=Result.SUCCESS,
            user_id=user.id,
            username=current_user,
            entity_id=host_id,
            entity_name=host.fqdn,
            details={
                "request_id": request_id,
                "packages": request.package_names,
                "requested_by": request.requested_by,
            },
        )

        return PackageUninstallResponse(
            success=True,
            message=_("Successfully queued %d packages for uninstallation")
            % len(request.package_names),
            request_id=request_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_("Failed to queue package uninstallation: %s") % str(e),
        ) from e


class PackageItem(BaseModel):
    """Individual package within an installation request."""

    package_name: str
    package_manager: str


class InstallationHistoryItem(BaseModel):
    """Response model for installation history item - now UUID-based."""

    request_id: str  # The UUID that groups packages
    requested_by: str
    status: str
    operation_type: str  # install or uninstall
    requested_at: datetime
    completed_at: Optional[datetime] = None
    installation_log: Optional[str] = None
    package_names: str  # Comma-separated list of package names


class InstallationHistoryResponse(BaseModel):
    """Response model for installation history."""

    installations: List[InstallationHistoryItem]
    total_count: int


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


class InstallationCompletionRequest(BaseModel):
    """Request from agent when installation completes."""

    request_id: str
    success: bool
    result_log: str


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
