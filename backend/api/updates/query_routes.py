"""API routes for querying package updates."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import sessionmaker
from backend.auth.auth_bearer import JWTBearer
from backend.i18n import _
from backend.persistence import db, models
from .constants import OS_UPGRADE_PACKAGE_MANAGERS
from .models import UpdateStatsSummary

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def get_update_summary(dependencies=Depends(JWTBearer())):
    """Get summary statistics for package updates across all hosts, including update results."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Count total hosts
            total_hosts = (
                session.query(models.Host).filter(models.Host.active.is_(True)).count()
            )

            # Count hosts with updates
            hosts_with_updates = (
                session.query(models.PackageUpdate.host_id).distinct().count()
            )

            # Count total updates
            total_updates = session.query(models.PackageUpdate).count()

            # Count security updates (based on update_type)
            security_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "security")
                .count()
            )

            # Count system updates (based on update_type)
            system_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "system")
                .count()
            )

            # Count application updates (based on update_type)
            application_updates = (
                session.query(models.PackageUpdate)
                .filter(models.PackageUpdate.update_type == "enhancement")
                .count()
            )

            # Count OS upgrades (based on package_manager)
            os_upgrades = (
                session.query(models.PackageUpdate)
                .filter(
                    models.PackageUpdate.package_manager.in_(
                        OS_UPGRADE_PACKAGE_MANAGERS
                    )
                )
                .count()
            )

            # Try to get update results from the update handlers module's cache
            update_results = {}
            try:
                import backend.api.update_handlers as update_handlers_module

                if hasattr(update_handlers_module, "handle_update_apply_result"):
                    handler = getattr(
                        update_handlers_module, "handle_update_apply_result"
                    )
                    if hasattr(handler, "update_results_cache"):
                        update_results = handler.update_results_cache.copy()
            except Exception:  # nosec B110
                pass  # If we can't get the cache, just return empty results

            return {
                "total_hosts": total_hosts,
                "hosts_with_updates": hosts_with_updates,
                "total_updates": total_updates,
                "security_updates": security_updates,
                "system_updates": system_updates,
                "application_updates": application_updates,
                "os_upgrades": os_upgrades,
                "results": update_results,
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get update summary: %s") % str(e)
        ) from e


@router.get("/{host_id}")
async def get_host_updates(
    host_id: str,
    *,
    package_manager: Optional[str] = Query(None),
    security_only: Optional[bool] = Query(None),
    system_only: Optional[bool] = Query(None),
    application_only: Optional[bool] = Query(None),
    dependencies=Depends(JWTBearer()),
):
    """Get package updates for a specific host."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Verify host exists
            host = session.query(models.Host).filter(models.Host.id == host_id).first()
            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            # Build query with filters
            query = session.query(models.PackageUpdate).filter(
                models.PackageUpdate.host_id == host_id
            )

            if package_manager:
                query = query.filter(
                    models.PackageUpdate.package_manager == package_manager
                )

            if security_only:
                query = query.filter(models.PackageUpdate.update_type == "security")

            if system_only:
                query = query.filter(models.PackageUpdate.update_type == "system")

            if application_only:
                query = query.filter(models.PackageUpdate.update_type == "enhancement")

            updates = query.order_by(models.PackageUpdate.package_name).all()

            # Convert to dict format
            update_list = []
            for update in updates:
                update_dict = {
                    "id": str(update.id),
                    "host_id": host_id,  # Add missing host_id
                    "hostname": host.fqdn,  # Add missing hostname
                    "package_name": update.package_name,
                    "current_version": update.current_version,
                    "available_version": update.available_version,
                    "package_manager": update.package_manager,
                    "update_type": update.update_type,
                    # Add frontend-expected boolean fields
                    "is_security_update": update.update_type == "security",
                    "is_system_update": update.update_type == "system",
                    "priority": update.priority,
                    "description": update.description,
                    "requires_reboot": update.requires_reboot,
                    "size_bytes": update.size_bytes,
                    "discovered_at": (
                        update.discovered_at.isoformat()
                        if update.discovered_at
                        else None
                    ),
                    "created_at": (
                        update.created_at.isoformat() if update.created_at else None
                    ),
                    "updated_at": (
                        update.updated_at.isoformat() if update.updated_at else None
                    ),
                }
                update_list.append(update_dict)

            return {
                "host_id": host_id,
                "hostname": host.fqdn,
                "updates": update_list,
                "total_updates": len(update_list),
                "security_updates": len(
                    [u for u in updates if u.update_type == "security"]
                ),
                "system_updates": len(
                    [u for u in updates if u.update_type == "system"]
                ),
                "application_updates": len(
                    [u for u in updates if u.update_type == "enhancement"]
                ),
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get host updates: %s") % str(e)
        ) from e


@router.get("/")
async def get_all_updates(  # pylint: disable=too-many-positional-arguments
    security_only: Optional[bool] = Query(None),
    system_only: Optional[bool] = Query(None),
    application_only: Optional[bool] = Query(None),
    package_manager: Optional[str] = Query(None),
    limit: Optional[int] = Query(100),
    offset: Optional[int] = Query(0),
    dependencies=Depends(JWTBearer()),
):
    """Get package updates across all hosts."""
    try:
        session_factory = sessionmaker(bind=db.get_engine())
        with session_factory() as session:
            # Build base query
            query = session.query(models.PackageUpdate, models.Host.fqdn).join(
                models.Host
            )

            # Apply filters
            if security_only:
                query = query.filter(models.PackageUpdate.update_type == "security")

            if system_only:
                query = query.filter(models.PackageUpdate.update_type == "system")

            if application_only:
                query = query.filter(models.PackageUpdate.update_type == "enhancement")

            if package_manager:
                query = query.filter(
                    models.PackageUpdate.package_manager == package_manager
                )

            # Get total count before pagination
            total_count = query.count()

            # Apply pagination and ordering
            updates_with_hosts = (
                query.order_by(
                    models.PackageUpdate.update_type,
                    models.Host.fqdn,
                    models.PackageUpdate.package_name,
                )
                .limit(limit)
                .offset(offset)
                .all()
            )

            # Format response
            update_list = []
            for update, hostname in updates_with_hosts:
                update_dict = {
                    "id": str(update.id),
                    "host_id": str(update.host_id),
                    "hostname": hostname,
                    "package_name": update.package_name,
                    "current_version": update.current_version,
                    "available_version": update.available_version,
                    "package_manager": update.package_manager,
                    "update_type": update.update_type,
                    # Add frontend-expected boolean fields
                    "is_security_update": update.update_type == "security",
                    "is_system_update": update.update_type == "system",
                    "priority": update.priority,
                    "description": update.description,
                    "requires_reboot": update.requires_reboot,
                    "size_bytes": update.size_bytes,
                    "discovered_at": (
                        update.discovered_at.isoformat()
                        if update.discovered_at
                        else None
                    ),
                    "created_at": (
                        update.created_at.isoformat() if update.created_at else None
                    ),
                    "updated_at": (
                        update.updated_at.isoformat() if update.updated_at else None
                    ),
                }
                update_list.append(update_dict)

            return {
                "updates": update_list,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Failed to get updates: %s") % str(e)
        ) from e


@router.get("/results", response_model=UpdateStatsSummary)
async def get_update_results(dependencies=Depends(JWTBearer())):
    """Get update results."""
    try:
        logger.info("SUCCESS: get_update_results called successfully")
        return UpdateStatsSummary(
            total_hosts=0,
            hosts_with_updates=0,
            total_updates=0,
            security_updates=0,
            system_updates=0,
            application_updates=0,
        )
    except Exception as e:
        logger.error("Error in get_update_results: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to get update results: %s") % str(e)
        ) from e


@router.get("/update-status")
async def get_update_status(dependencies=Depends(JWTBearer())):
    """Get update status."""
    try:
        import backend.api.agent as agent_module

        if hasattr(agent_module, "handle_update_apply_result"):
            handler = getattr(agent_module, "handle_update_apply_result")
            if hasattr(handler, "update_results_cache"):
                return {"results": handler.update_results_cache.copy()}
        return {"results": {}}
    except Exception as e:
        logger.error("Error fetching update status: %s", e)
        return {"results": {}, "error": "Failed to fetch update status"}
