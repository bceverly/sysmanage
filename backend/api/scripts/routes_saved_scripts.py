"""
API routes for saved script management (CRUD operations).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import sessionmaker

from backend.api.error_constants import error_script_not_found, error_user_not_found
from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.security.roles import SecurityRoles
from backend.services.audit_service import ActionType, AuditService, EntityType, Result
from backend.utils.verbosity_logger import sanitize_log

from .models import SavedScriptCreate, SavedScriptResponse, SavedScriptUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_scripts_sync(
    platform: Optional[str], active_only: bool
) -> List[SavedScriptResponse]:
    """
    Synchronous helper function to retrieve saved scripts.
    This runs in a thread pool to avoid blocking the event loop.
    """
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            query = db_session.query(models.SavedScript)

            if active_only:
                query = query.filter(models.SavedScript.is_active.is_(True))

            if platform:
                query = query.filter(
                    or_(
                        models.SavedScript.platform == platform,
                        models.SavedScript.platform.is_(None),
                    )
                )

            query = query.order_by(models.SavedScript.name)
            scripts = query.all()

            return [
                SavedScriptResponse(
                    id=str(script.id),
                    name=script.name,
                    description=script.description,
                    content=script.content,
                    shell_type=script.shell_type,
                    platform=script.platform,
                    run_as_user=script.run_as_user,
                    is_active=script.is_active,
                    created_by=script.created_by,
                    created_at=script.created_at,
                    updated_at=script.updated_at,
                )
                for script in scripts
            ]

    except Exception as e:
        logger.error("Error fetching saved scripts: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch saved scripts")
        ) from e


@router.get("/", response_model=List[SavedScriptResponse])
async def get_saved_scripts(
    current_user=Depends(get_current_user),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    active_only: bool = Query(True, description="Show only active scripts"),
):
    """
    Get all saved scripts.
    Runs the database query in a thread pool to avoid blocking the event loop.
    """
    # Run the synchronous database operation in a thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_scripts_sync, platform, active_only)


@router.post("/", response_model=SavedScriptResponse)
async def create_saved_script(
    script_data: SavedScriptCreate,
    current_user=Depends(get_current_user),
):
    """Create a new saved script."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to add scripts
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.ADD_SCRIPT):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: ADD_SCRIPT role required"),
                )

            # Check for duplicate name
            existing = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.name == script_data.name)
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=400, detail=_("A script with this name already exists")
                )

            # Create new script
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            script = models.SavedScript(
                name=script_data.name,
                description=script_data.description,
                content=script_data.content,
                shell_type=script_data.shell_type,
                platform=script_data.platform,
                run_as_user=script_data.run_as_user,
                is_active=True,
                created_by=current_user,
                created_at=now,
                updated_at=now,
            )

            db_session.add(script)
            db_session.commit()
            db_session.refresh(script)

            # Log the creation to audit log
            AuditService.log_create(
                db=db_session,
                entity_type=EntityType.SCRIPT,
                entity_id=str(script.id),
                entity_name=script.name,
                user_id=auth_user.id,
                username=current_user,
                details={
                    "description": script.description,
                    "shell_type": script.shell_type,
                    "platform": script.platform,
                    "run_as_user": script.run_as_user,
                },
            )

            logger.info(
                "Created saved script '%s' by user %s", script.name, current_user
            )
            return SavedScriptResponse(
                id=str(script.id),
                name=script.name,
                description=script.description,
                content=script.content,
                shell_type=script.shell_type,
                platform=script.platform,
                run_as_user=script.run_as_user,
                is_active=script.is_active,
                created_by=script.created_by,
                created_at=script.created_at,
                updated_at=script.updated_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating saved script: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to create saved script")
        ) from e


@router.get("/{script_id}", response_model=SavedScriptResponse)
async def get_saved_script(
    script_id: str,
    current_user=Depends(get_current_user),
):
    """Get a specific saved script by ID."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=error_script_not_found())

            return SavedScriptResponse(
                id=str(script.id),
                name=script.name,
                description=script.description,
                content=script.content,
                shell_type=script.shell_type,
                platform=script.platform,
                run_as_user=script.run_as_user,
                is_active=script.is_active,
                created_by=script.created_by,
                created_at=script.created_at,
                updated_at=script.updated_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching saved script %s: %s", sanitize_log(script_id), e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch saved script")
        ) from e


@router.put("/{script_id}", response_model=SavedScriptResponse)
async def update_saved_script(
    script_id: str,
    script_data: SavedScriptUpdate,
    current_user=Depends(get_current_user),
):
    """Update an existing saved script."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to edit scripts
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.EDIT_SCRIPT):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: EDIT_SCRIPT role required"),
                )

            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=error_script_not_found())

            # Check for duplicate name if name is being changed
            if script_data.name and script_data.name != script.name:
                existing = (
                    db_session.query(models.SavedScript)
                    .filter(
                        and_(
                            models.SavedScript.name == script_data.name,
                            models.SavedScript.id != script_id,
                        )
                    )
                    .first()
                )

                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail=_("A script with this name already exists"),
                    )

            # Update script fields
            update_data = script_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(script, field, value)

            script.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            db_session.commit()
            db_session.refresh(script)

            # Log the update to audit log
            AuditService.log_update(
                db=db_session,
                entity_type=EntityType.SCRIPT,
                entity_id=str(script.id),
                entity_name=script.name,
                user_id=auth_user.id,
                username=current_user,
                details={
                    "updated_fields": list(update_data.keys()),
                    "description": script.description,
                    "shell_type": script.shell_type,
                    "platform": script.platform,
                    "run_as_user": script.run_as_user,
                    "is_active": script.is_active,
                },
            )

            logger.info("Updated saved script %d by user %s", script_id, current_user)
            return SavedScriptResponse(
                id=str(script.id),
                name=script.name,
                description=script.description,
                content=script.content,
                shell_type=script.shell_type,
                platform=script.platform,
                run_as_user=script.run_as_user,
                is_active=script.is_active,
                created_by=script.created_by,
                created_at=script.created_at,
                updated_at=script.updated_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating saved script %s: %s", sanitize_log(script_id), e)
        raise HTTPException(
            status_code=500, detail=_("Failed to update saved script")
        ) from e


@router.delete("/{script_id}")
async def delete_saved_script(
    script_id: str,
    current_user=Depends(get_current_user),
):
    """Delete a saved script."""
    session_factory = sessionmaker(bind=db.get_engine())
    try:
        with session_factory() as db_session:
            # Check if user has permission to delete scripts
            auth_user = (
                db_session.query(models.User)
                .filter(models.User.userid == current_user)
                .first()
            )
            if not auth_user:
                raise HTTPException(status_code=401, detail=error_user_not_found())

            if auth_user._role_cache is None:
                auth_user.load_role_cache(db_session)

            if not auth_user.has_role(SecurityRoles.DELETE_SCRIPT):
                raise HTTPException(
                    status_code=403,
                    detail=_("Permission denied: DELETE_SCRIPT role required"),
                )

            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=error_script_not_found())

            # Check if script is being used in any pending/running executions
            active_executions = (
                db_session.query(models.ScriptExecutionLog)
                .filter(
                    and_(
                        models.ScriptExecutionLog.saved_script_id == script_id,
                        models.ScriptExecutionLog.status.in_(["pending", "running"]),
                    )
                )
                .count()
            )

            if active_executions > 0:
                raise HTTPException(
                    status_code=400,
                    detail=_("Cannot delete script with active executions"),
                )

            script_name = script.name

            db_session.delete(script)
            db_session.commit()

            # Log the deletion to audit log
            AuditService.log_delete(
                db=db_session,
                entity_type=EntityType.SCRIPT,
                entity_id=str(script_id),
                entity_name=script_name,
                user_id=auth_user.id,
                username=current_user,
                details={
                    "description": script.description,
                    "shell_type": script.shell_type,
                    "platform": script.platform,
                },
            )

            logger.info("Deleted saved script %d by user %s", script_id, current_user)
            return {"message": _("Script deleted successfully")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting saved script %s: %s", sanitize_log(script_id), e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete saved script")
        ) from e
