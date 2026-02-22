"""
This module houses the API routes for audit log viewing in SysManage.

Provides endpoints for viewing audit log entries with filtering capabilities.
Advanced audit features (CSV/JSON/CEF/LEEF export, retention policies, archival)
are provided by the audit_engine Professional+ module.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, sessionmaker

from backend.api.error_constants import error_user_not_found
from backend.auth.auth_bearer import JWTBearer, get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence import models
from backend.persistence.db import get_db
from backend.security.roles import SecurityRoles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])


class AuditLogEntryResponse(BaseModel):
    """Response model for a single audit log entry."""

    id: str
    timestamp: datetime
    user_id: Optional[str] = None
    username: Optional[str] = None
    action_type: str
    entity_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    description: str
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    result: str
    error_message: Optional[str] = None
    category: Optional[str] = None
    entry_type: Optional[str] = None

    @validator("id", "user_id", pre=True)
    def convert_uuid_to_string(cls, value):  # pylint: disable=no-self-argument
        """Convert UUID objects to strings."""
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Response model for paginated list of audit log entries."""

    total: int
    limit: int
    offset: int
    entries: List[AuditLogEntryResponse]


@router.get("/list", response_model=AuditLogListResponse)
async def list_audit_logs(  # NOSONAR
    user_id: Optional[str] = Query(None, description=_("Filter by user ID")),
    action_type: Optional[str] = Query(None, description=_("Filter by action type")),
    entity_type: Optional[str] = Query(None, description=_("Filter by entity type")),
    category: Optional[str] = Query(None, description=_("Filter by category")),
    entry_type: Optional[str] = Query(None, description=_("Filter by entry type")),
    search: Optional[str] = Query(
        None, description=_("Search in description and entity name")
    ),
    start_date: Optional[datetime] = Query(
        None,
        description=_("Filter by start date (ISO format, defaults to 4 hours ago)"),
    ),
    end_date: Optional[datetime] = Query(
        None, description=_("Filter by end date (ISO format, defaults to now)")
    ),
    limit: int = Query(
        100, ge=1, le=1000, description=_("Number of entries to return")
    ),
    offset: int = Query(0, ge=0, description=_("Number of entries to skip")),
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """
    List audit log entries with optional filtering.

    Requires VIEW_AUDIT_LOG role.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        # Check if user has permission to view audit logs
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)

        if not auth_user.has_role(SecurityRoles.VIEW_AUDIT_LOG):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_AUDIT_LOG role required"),
            )

    try:
        # Default to last 4 hours if no date range specified
        if start_date is None and end_date is None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start_date = now - timedelta(hours=4)
            end_date = now
        elif start_date is None and end_date is not None:
            # If only end_date provided, use it
            pass
        elif start_date is not None and end_date is None:
            # If only start_date provided, use current time as end
            end_date = datetime.now(timezone.utc).replace(tzinfo=None)

        # Build query with filters
        query = db_session.query(models.AuditLog)

        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
                query = query.filter(models.AuditLog.user_id == user_uuid)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=_("Invalid user ID format")
                ) from exc

        if action_type:
            query = query.filter(models.AuditLog.action_type == action_type)

        if entity_type:
            query = query.filter(models.AuditLog.entity_type == entity_type)

        if category:
            query = query.filter(models.AuditLog.category == category)

        if entry_type:
            query = query.filter(models.AuditLog.entry_type == entry_type)

        if search:
            # Search in description and entity_name using case-insensitive LIKE
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    models.AuditLog.description.ilike(search_pattern),
                    models.AuditLog.entity_name.ilike(search_pattern),
                )
            )

        if start_date:
            query = query.filter(models.AuditLog.timestamp >= start_date)

        if end_date:
            query = query.filter(models.AuditLog.timestamp <= end_date)

        # Get total count before pagination
        total = query.count()

        # Apply ordering (most recent first) and pagination
        entries = (
            query.order_by(models.AuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        logger.info(
            "Audit log query by user %s: %d results (offset=%d, limit=%d)",
            current_user,
            total,
            offset,
            limit,
        )

        return AuditLogListResponse(
            total=total, limit=limit, offset=offset, entries=entries
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing audit logs: %s", e)
        raise HTTPException(
            status_code=500, detail=_("Failed to retrieve audit logs: %s") % str(e)
        ) from e


@router.get("/{audit_id}", response_model=AuditLogEntryResponse)
async def get_audit_log_entry(
    audit_id: str,
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """
    Get a single audit log entry by ID.

    Requires VIEW_AUDIT_LOG role.
    """
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
        # Check if user has permission to view audit logs
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=error_user_not_found())

        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)

        if not auth_user.has_role(SecurityRoles.VIEW_AUDIT_LOG):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_AUDIT_LOG role required"),
            )

    try:
        # Parse audit ID
        try:
            audit_uuid = uuid.UUID(audit_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=_("Invalid audit log ID format")
            ) from exc

        # Query for the specific entry
        entry = (
            db_session.query(models.AuditLog)
            .filter(models.AuditLog.id == audit_uuid)
            .first()
        )

        if not entry:
            raise HTTPException(status_code=404, detail=_("Audit log entry not found"))

        logger.info("Audit log entry %s retrieved by user %s", audit_id, current_user)

        return entry

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving audit log entry %s: %s", audit_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve audit log entry: %s") % str(e),
        ) from e


@router.get("/export")
async def export_audit_logs(
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """
    Export audit log entries.

    This is a Pro+ feature. Requires the audit_engine module for
    CSV, JSON, CEF, and LEEF export formats.
    """
    audit_engine = module_loader.get_module("audit_engine")
    if audit_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Audit log export requires a SysManage Professional+ license. "
                "Please upgrade to access CSV, JSON, CEF, and LEEF export formats."
            ),
        )
    raise HTTPException(
        status_code=307,
        detail=_("Use /api/v1/audit/export with Pro+ license"),
        headers={"Location": "/api/v1/audit/export"},
    )
