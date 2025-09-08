"""
This module houses the API routes for script management in SysManage.
Handles saved scripts creation/editing and script execution requests.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, validator
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import sessionmaker

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import db, models
from backend.websocket.queue_manager import (
    server_queue_manager,
    QueueDirection,
    Priority,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for API
class SavedScriptCreate(BaseModel):
    """Request model for creating a saved script."""

    name: str
    description: Optional[str] = None
    content: str
    shell_type: str
    platform: Optional[str] = None
    run_as_user: Optional[str] = None

    @validator("name")
    def validate_name(cls, value):  # pylint: disable=no-self-argument
        if not value or len(value.strip()) == 0:
            raise ValueError(_("Script name cannot be empty"))
        if len(value) > 255:
            raise ValueError(_("Script name cannot exceed 255 characters"))
        return value.strip()

    @validator("shell_type")
    def validate_shell_type(cls, value):  # pylint: disable=no-self-argument
        allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
        if value not in allowed_shells:
            raise ValueError(_("Unsupported shell type: {}").format(value))
        return value

    @validator("content")
    def validate_content(cls, value):  # pylint: disable=no-self-argument
        if not value or len(value.strip()) == 0:
            raise ValueError(_("Script content cannot be empty"))
        return value


class SavedScriptUpdate(BaseModel):
    """Request model for updating a saved script."""

    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    shell_type: Optional[str] = None
    platform: Optional[str] = None
    run_as_user: Optional[str] = None
    is_active: Optional[bool] = None

    @validator("name", pre=True)
    def validate_name(cls, value):  # pylint: disable=no-self-argument
        if value is not None and (not value or len(value.strip()) == 0):
            raise ValueError(_("Script name cannot be empty"))
        if value is not None and len(value) > 255:
            raise ValueError(_("Script name cannot exceed 255 characters"))
        return value.strip() if value else None

    @validator("shell_type")
    def validate_shell_type(cls, value):  # pylint: disable=no-self-argument
        if value is not None:
            allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
            if value not in allowed_shells:
                raise ValueError(_("Unsupported shell type: {}").format(value))
        return value

    @validator("content", pre=True)
    def validate_content(cls, value):  # pylint: disable=no-self-argument
        if value is not None and (not value or len(value.strip()) == 0):
            raise ValueError(_("Script content cannot be empty"))
        return value


class ScriptExecutionRequest(BaseModel):
    """Request model for executing a script."""

    host_id: int
    saved_script_id: Optional[int] = None
    script_name: Optional[str] = None
    script_content: Optional[str] = None
    shell_type: Optional[str] = None
    run_as_user: Optional[str] = None

    @validator("script_content")
    def validate_script_content_or_saved_id(
        cls, value, values
    ):  # pylint: disable=no-self-argument,invalid-name
        saved_script_id = values.get("saved_script_id")
        if not saved_script_id and (not value or len(value.strip()) == 0):
            raise ValueError(
                _("Either saved_script_id or script_content must be provided")
            )
        return value

    @validator("shell_type")
    def validate_shell_type_for_adhoc(
        cls, value, values
    ):  # pylint: disable=no-self-argument
        saved_script_id = values.get("saved_script_id")
        if not saved_script_id and not value:
            raise ValueError(_("shell_type is required for ad-hoc scripts"))
        if value:
            allowed_shells = ["bash", "sh", "zsh", "powershell", "cmd", "ksh"]
            if value not in allowed_shells:
                raise ValueError(_("Unsupported shell type: {}").format(value))
        return value


class SavedScriptResponse(BaseModel):
    """Response model for saved script data."""

    id: int
    name: str
    description: Optional[str]
    content: str
    shell_type: str
    platform: Optional[str]
    run_as_user: Optional[str]
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScriptExecutionResponse(BaseModel):
    """Response model for script execution status."""

    execution_id: str
    status: str
    message: str

    class Config:
        from_attributes = True


class ScriptExecutionLogResponse(BaseModel):
    """Response model for script execution log."""

    id: int
    host_id: int
    host_fqdn: Optional[str]
    saved_script_id: Optional[int]
    script_name: Optional[str]
    shell_type: str
    run_as_user: Optional[str]
    requested_by: str
    execution_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    exit_code: Optional[int]
    stdout_output: Optional[str]
    stderr_output: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScriptExecutionsResponse(BaseModel):
    """Paginated response model for script execution logs."""

    executions: List[ScriptExecutionLogResponse]
    total: int
    page: int
    pages: int


# API Routes


@router.get("/", response_model=List[SavedScriptResponse])
async def get_saved_scripts(
    current_user=Depends(get_current_user),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    active_only: bool = Query(True, description="Show only active scripts"),
):
    """Get all saved scripts."""
    session_factory = sessionmaker(bind=db.engine)
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

            return [SavedScriptResponse.from_orm(script) for script in scripts]

    except Exception as e:
        logger.error("Error fetching saved scripts: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch saved scripts")
        ) from e


@router.post("/", response_model=SavedScriptResponse)
async def create_saved_script(
    script_data: SavedScriptCreate,
    current_user=Depends(get_current_user),
):
    """Create a new saved script."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
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
            now = datetime.now(timezone.utc)
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

            logger.info(
                "Created saved script '%s' by user %s", script.name, current_user
            )
            return SavedScriptResponse.from_orm(script)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating saved script: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to create saved script")
        ) from e


@router.get("/{script_id}", response_model=SavedScriptResponse)
async def get_saved_script(
    script_id: int,
    current_user=Depends(get_current_user),
):
    """Get a specific saved script by ID."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=_("Script not found"))

            return SavedScriptResponse.from_orm(script)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching saved script %d: %s", script_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch saved script")
        ) from e


@router.put("/{script_id}", response_model=SavedScriptResponse)
async def update_saved_script(
    script_id: int,
    script_data: SavedScriptUpdate,
    current_user=Depends(get_current_user),
):
    """Update an existing saved script."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=_("Script not found"))

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

            script.updated_at = datetime.now(timezone.utc)

            db_session.commit()
            db_session.refresh(script)

            logger.info("Updated saved script %d by user %s", script_id, current_user)
            return SavedScriptResponse.from_orm(script)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating saved script %d: %s", script_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to update saved script")
        ) from e


@router.delete("/{script_id}")
async def delete_saved_script(
    script_id: int,
    current_user=Depends(get_current_user),
):
    """Delete a saved script."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            script = (
                db_session.query(models.SavedScript)
                .filter(models.SavedScript.id == script_id)
                .first()
            )

            if not script:
                raise HTTPException(status_code=404, detail=_("Script not found"))

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

            db_session.delete(script)
            db_session.commit()

            logger.info("Deleted saved script %d by user %s", script_id, current_user)
            return {"message": _("Script deleted successfully")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting saved script %d: %s", script_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete saved script")
        ) from e


@router.post("/execute", response_model=ScriptExecutionResponse)
async def execute_script(
    execution_request: ScriptExecutionRequest,
    current_user=Depends(get_current_user),
):
    """Execute a script on a remote host."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            # Verify host exists and is active
            host = (
                db_session.query(models.Host)
                .filter(models.Host.id == execution_request.host_id)
                .first()
            )

            if not host:
                raise HTTPException(status_code=404, detail=_("Host not found"))

            if not host.active:
                raise HTTPException(status_code=400, detail=_("Host is not active"))

            # Prepare script execution data
            execution_id = str(uuid.uuid4())
            script_content = execution_request.script_content
            shell_type = execution_request.shell_type
            script_name = execution_request.script_name

            # If using saved script, fetch its details
            if execution_request.saved_script_id:
                saved_script = (
                    db_session.query(models.SavedScript)
                    .filter(models.SavedScript.id == execution_request.saved_script_id)
                    .first()
                )

                if not saved_script:
                    raise HTTPException(
                        status_code=404, detail=_("Saved script not found")
                    )

                if not saved_script.is_active:
                    raise HTTPException(
                        status_code=400, detail=_("Script is not active")
                    )

                script_content = saved_script.content
                shell_type = saved_script.shell_type
                script_name = saved_script.name

                # Use saved script's run_as_user if not overridden
                if not execution_request.run_as_user:
                    execution_request.run_as_user = saved_script.run_as_user

            # Create execution log entry
            now = datetime.now(timezone.utc)
            execution_log = models.ScriptExecutionLog(
                host_id=execution_request.host_id,
                saved_script_id=execution_request.saved_script_id,
                script_name=script_name,
                script_content=script_content,
                shell_type=shell_type,
                run_as_user=execution_request.run_as_user,
                requested_by=current_user,
                execution_id=execution_id,
                status="pending",
                created_at=now,
                updated_at=now,
            )

            db_session.add(execution_log)
            # Don't commit yet - queue the message in the same transaction

            # Queue script execution command for outbound delivery to agent
            command_data = {
                "execution_id": execution_id,
                "script_content": script_content,
                "shell_type": shell_type,
                "run_as_user": execution_request.run_as_user,
                "script_name": script_name or "ad-hoc script",
            }

            # Queue the message for delivery to the agent
            logger.info(
                "Queueing script execution to host %d (%s)",
                host.id,
                host.fqdn,
            )

            try:
                queue_message_id = server_queue_manager.enqueue_message(
                    message_type="command",
                    message_data=command_data,
                    direction=QueueDirection.OUTBOUND,
                    host_id=host.id,
                    priority=Priority.HIGH,
                    correlation_id=execution_id,
                    db=db_session,
                )

                # Now commit both the execution log AND the queued message together
                db_session.commit()

                logger.info(
                    "Script execution %s queued with message ID %s for host %d (%s)",
                    execution_id,
                    queue_message_id,
                    host.id,
                    host.fqdn,
                )
            except Exception as e:
                # Update execution log to failed
                execution_log.status = "failed"
                execution_log.error_message = _(
                    "Failed to queue script execution: {}"
                ).format(str(e))
                execution_log.updated_at = datetime.now(timezone.utc)
                db_session.commit()

                logger.error("Failed to queue script execution: %s", e)
                raise HTTPException(
                    status_code=500,
                    detail=_("Failed to queue script execution"),
                ) from e

            logger.info(
                "Script execution %s requested by %s for host %d",
                execution_id,
                current_user,
                execution_request.host_id,
            )

            return ScriptExecutionResponse(
                execution_id=execution_id,
                status="pending",
                message=_("Script execution queued for delivery"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error executing script: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to execute script")
        ) from e


@router.get("/executions/", response_model=ScriptExecutionsResponse)
async def get_script_executions(
    current_user=Depends(get_current_user),
    host_id: Optional[int] = Query(None, description="Filter by host ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, description="Page number (1-based)"),
    limit: int = Query(50, description="Maximum number of results per page"),
):
    """Get script execution logs with pagination."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            # Build base query
            base_query = db_session.query(models.ScriptExecutionLog).join(
                models.Host, models.ScriptExecutionLog.host_id == models.Host.id
            )

            if host_id:
                base_query = base_query.filter(
                    models.ScriptExecutionLog.host_id == host_id
                )

            if status:
                base_query = base_query.filter(
                    models.ScriptExecutionLog.status == status
                )

            # Get total count
            total = base_query.count()

            # Calculate offset and pages
            offset = (page - 1) * limit
            pages = (total + limit - 1) // limit if total > 0 else 1

            # Get paginated results
            query = base_query.order_by(desc(models.ScriptExecutionLog.created_at))
            query = query.offset(offset).limit(limit)

            executions = query.all()

            # Add host FQDN to response
            execution_results = []
            for execution in executions:
                execution_dict = execution.__dict__.copy()
                execution_dict["host_fqdn"] = execution.host.fqdn
                execution_results.append(ScriptExecutionLogResponse(**execution_dict))

            return ScriptExecutionsResponse(
                executions=execution_results, total=total, page=page, pages=pages
            )

    except Exception as e:
        logger.error("Error fetching script executions: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch script executions")
        ) from e


@router.delete("/executions/{execution_id}")
async def delete_script_execution(
    execution_id: str,
    current_user=Depends(get_current_user),
):
    """Delete a specific script execution by execution ID."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            execution = (
                db_session.query(models.ScriptExecutionLog)
                .filter(models.ScriptExecutionLog.execution_id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(
                    status_code=404, detail=_("Script execution not found")
                )

            db_session.delete(execution)
            db_session.commit()

            logger.info(
                "Deleted script execution %s by user %s", execution_id, current_user
            )
            return {"message": _("Script execution deleted successfully")}
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error("Error deleting script execution %s: %s", execution_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete script execution")
        ) from e


@router.delete("/executions/bulk")
async def delete_script_executions_bulk(
    execution_ids: List[str] = Body(...),
    current_user=Depends(get_current_user),
):
    """Delete multiple script executions by execution IDs."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            deleted_count = (
                db_session.query(models.ScriptExecutionLog)
                .filter(models.ScriptExecutionLog.execution_id.in_(execution_ids))
                .delete(synchronize_session=False)
            )

            db_session.commit()

            logger.info(
                "Bulk deleted %d script executions by user %s",
                deleted_count,
                current_user,
            )
            return {
                "message": _("Script executions deleted successfully"),
                "deleted_count": deleted_count,
            }
    except Exception as e:
        db_session.rollback()
        logger.error("Error bulk deleting script executions: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to delete script executions")
        ) from e


@router.get("/executions/{execution_id}", response_model=ScriptExecutionLogResponse)
async def get_script_execution(
    execution_id: str,
    current_user=Depends(get_current_user),
):
    """Get a specific script execution by execution ID."""
    session_factory = sessionmaker(bind=db.engine)
    try:
        with session_factory() as db_session:
            execution = (
                db_session.query(models.ScriptExecutionLog)
                .join(models.Host, models.ScriptExecutionLog.host_id == models.Host.id)
                .filter(models.ScriptExecutionLog.execution_id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(
                    status_code=404, detail=_("Script execution not found")
                )

            execution_dict = execution.__dict__.copy()
            execution_dict["host_fqdn"] = execution.host.fqdn

            return ScriptExecutionLogResponse(**execution_dict)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching script execution %s: %s", execution_id, e)
        raise HTTPException(
            status_code=500, detail=_("Failed to fetch script execution")
        ) from e
