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
from backend.utils.verbosity_logger import sanitize_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-log", tags=["audit-log"])


# Reused 403 detail string — extracted so the wording can't drift
# between handlers and so SonarQube's duplication scanner is happy.
_ERR_VIEW_AUDIT_LOG_DENIED = "Permission denied: VIEW_AUDIT_LOG role required"


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


class AuditLogFilters:
    """Bundle of optional filters consumed by /list and /export.

    Declared as a class with FastAPI ``Query`` defaults so the OpenAPI
    spec still shows each parameter individually, while collapsing 9
    parameters into one for the route signature (keeps Sonar's 13-param
    cap happy)."""

    def __init__(
        self,
        user_id: Optional[str] = Query(None, description="Filter by user ID"),
        action_type: Optional[str] = Query(None, description="Filter by action type"),
        entity_type: Optional[str] = Query(None, description="Filter by entity type"),
        result: Optional[str] = Query(
            None, description="Filter by result (SUCCESS, FAILURE, PENDING)"
        ),
        category: Optional[str] = Query(None, description="Filter by category"),
        entry_type: Optional[str] = Query(None, description="Filter by entry type"),
        search: Optional[str] = Query(
            None, description="Search in description and entity name"
        ),
        start_date: Optional[datetime] = Query(
            None, description="Filter by start date (ISO format)"
        ),
        end_date: Optional[datetime] = Query(
            None, description="Filter by end date (ISO format)"
        ),
    ):
        self.user_id = user_id
        self.action_type = action_type
        self.entity_type = entity_type
        self.result = result
        self.category = category
        self.entry_type = entry_type
        self.search = search
        self.start_date = start_date
        self.end_date = end_date


def _apply_audit_filters(query, filters: AuditLogFilters):
    """Apply each of ``filters``'s set fields to ``query`` and return
    the narrowed query.  Extracted so /list and /export share the
    same filter shape AND so the cognitive complexity of the routes
    stays under SonarQube's threshold."""
    if filters.user_id:
        try:
            query = query.filter(models.AuditLog.user_id == uuid.UUID(filters.user_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=_("Invalid user ID format")
            ) from exc
    if filters.action_type:
        query = query.filter(models.AuditLog.action_type == filters.action_type)
    if filters.entity_type:
        query = query.filter(models.AuditLog.entity_type == filters.entity_type)
    if filters.result:
        query = query.filter(models.AuditLog.result == filters.result)
    if filters.category:
        query = query.filter(models.AuditLog.category == filters.category)
    if filters.entry_type:
        query = query.filter(models.AuditLog.entry_type == filters.entry_type)
    if filters.search:
        pattern = f"%{filters.search}%"
        query = query.filter(
            or_(
                models.AuditLog.description.ilike(pattern),
                models.AuditLog.entity_name.ilike(pattern),
            )
        )
    if filters.start_date:
        query = query.filter(models.AuditLog.timestamp >= filters.start_date)
    if filters.end_date:
        query = query.filter(models.AuditLog.timestamp <= filters.end_date)
    return query


def _authorize_view_audit_log(db_session: Session, current_user: str) -> None:
    """Raise 401/403 if the caller can't view audit logs.  Shared by
    /list, /{id}, and /export."""
    session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    with session_local() as session:
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
            raise HTTPException(status_code=403, detail=_(_ERR_VIEW_AUDIT_LOG_DENIED))


def _default_date_range(filters: AuditLogFilters) -> AuditLogFilters:
    """If neither start nor end is set, default to the last 4 hours.
    Otherwise normalize the open-ended cases."""
    if filters.start_date is None and filters.end_date is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        filters.start_date = now - timedelta(hours=4)
        filters.end_date = now
    elif filters.start_date is not None and filters.end_date is None:
        filters.end_date = datetime.now(timezone.utc).replace(tzinfo=None)
    return filters


@router.get("/list", response_model=AuditLogListResponse)
async def list_audit_logs(
    filters: AuditLogFilters = Depends(),
    limit: int = Query(
        100, ge=1, le=1000, description=_("Number of entries to return")
    ),
    offset: int = Query(0, ge=0, description=_("Number of entries to skip")),
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """List audit log entries with optional filtering.

    Requires VIEW_AUDIT_LOG role."""
    _authorize_view_audit_log(db_session, current_user)
    try:
        filters = _default_date_range(filters)
        query = _apply_audit_filters(db_session.query(models.AuditLog), filters)
        total = query.count()
        entries = (
            query.order_by(models.AuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        logger.info(
            "Audit log query by user %s: %d results (offset=%d, limit=%d)",
            sanitize_log(current_user),
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
    _authorize_view_audit_log(db_session, current_user)
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

        logger.info(
            "Audit log entry %s retrieved by user %s",
            sanitize_log(audit_id),
            sanitize_log(current_user),
        )

        return entry

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving audit log entry %s: %s", audit_id, e)
        raise HTTPException(
            status_code=500,
            detail=_("Failed to retrieve audit log entry: %s") % str(e),
        ) from e


def _route_pro_plus_export(fmt_lower: str):
    """Pro+ formats (json/cef/leef) route to the audit_engine module
    when licensed; otherwise return a 402.  Pulled out so the export
    handler stays under SonarQube's complexity threshold."""
    audit_engine = module_loader.get_module("audit_engine")
    if audit_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "%s export requires a SysManage Professional+ license. "
                "OSS tier supports CSV export."
            )
            % fmt_lower.upper(),
        )
    raise HTTPException(
        status_code=307,
        detail=_("Use /api/v1/audit/export with Pro+ license"),
        headers={"Location": "/api/v1/audit/export"},
    )


@router.get("/export")
async def export_audit_logs(
    filters: AuditLogFilters = Depends(),
    fmt: str = Query(
        "csv", description=_("Export format: csv, pdf (OSS); json/cef/leef (Pro+)")
    ),
    db_session: Session = Depends(get_db),
    dependencies=Depends(JWTBearer()),
    current_user: str = Depends(get_current_user),
):
    """Export audit log entries.

    OSS tier ships ``fmt=csv`` and ``fmt=pdf``.  Pro+ audit_engine adds
    ``json``, ``cef``, and ``leef`` for SIEM integration.  Output uses
    the same filters as the /list endpoint so operators can export
    exactly what they were viewing.  Stream is unbounded (no /list
    limit/offset) — large filtered ranges may take a few seconds to
    materialize.

    Requires VIEW_AUDIT_LOG role."""
    _authorize_view_audit_log(db_session, current_user)
    fmt_lower = (fmt or "csv").lower()
    if fmt_lower in ("json", "cef", "leef"):
        _route_pro_plus_export(fmt_lower)
    if fmt_lower not in ("csv", "pdf"):
        raise HTTPException(
            status_code=400,
            detail=_("Unsupported export format: %s") % fmt,
        )

    query = _apply_audit_filters(db_session.query(models.AuditLog), filters)
    entries = query.order_by(models.AuditLog.timestamp.desc()).all()
    logger.info(
        "Audit log %s export by %s: %d entries",
        fmt_lower.upper(),
        sanitize_log(current_user),
        len(entries),
    )
    if fmt_lower == "pdf":
        return _stream_audit_pdf(entries)
    return _stream_audit_csv(entries)


_CSV_COLUMNS = [
    "timestamp",
    "user_id",
    "username",
    "action_type",
    "entity_type",
    "entity_id",
    "entity_name",
    "result",
    "description",
    "ip_address",
    "user_agent",
    "category",
    "entry_type",
    "error_message",
]


def _fmt_iso(value):
    """Format a datetime as ISO-8601, or return empty string when missing."""
    return value.isoformat() if value else ""


def _fmt_str(value):
    """Stringify a value, or return empty string when falsy.  Used for
    UUID columns where we want the str() representation."""
    return str(value) if value else ""


def _audit_log_row(entry) -> List[str]:
    """Pluck the CSV-export columns from one ``AuditLog`` row.  Order
    must match ``_CSV_COLUMNS``.  Pulled to module scope (rather than
    nested in ``_stream_audit_csv``) so its conditional-formatting
    cognitive complexity doesn't push the streamer past the SonarQube
    threshold."""
    return [
        _fmt_iso(entry.timestamp),
        _fmt_str(entry.user_id),
        entry.username or "",
        entry.action_type or "",
        entry.entity_type or "",
        _fmt_str(entry.entity_id),
        entry.entity_name or "",
        entry.result or "",
        entry.description or "",
        entry.ip_address or "",
        entry.user_agent or "",
        entry.category or "",
        entry.entry_type or "",
        entry.error_message or "",
    ]


def _stream_audit_csv(entries):
    """Stream a CSV of audit-log entries — RFC 4180 compliant."""
    import csv  # local import — only needed on this code path
    import io
    from fastapi.responses import StreamingResponse

    def _generator():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(_CSV_COLUMNS)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for entry in entries:
            writer.writerow(_audit_log_row(entry))
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(
        _generator(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-log-'
                f'{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}.csv"'
            ),
        },
    )


# Columns the PDF renderer emits.  Fewer than the CSV columns because
# PDF page-width is the binding constraint and several CSV columns
# (user_id, entity_id, user_agent, error_message) are too long or too
# operator-irrelevant to fit alongside the description.  Operators who
# need the wider set should still use CSV.
_PDF_COLUMNS = [
    ("Timestamp", _fmt_iso, "timestamp"),
    ("User", lambda e: e.username or "", "username"),
    ("Action", lambda e: e.action_type or "", "action_type"),
    ("Entity", lambda e: e.entity_type or "", "entity_type"),
    ("Name", lambda e: e.entity_name or "", "entity_name"),
    ("Result", lambda e: e.result or "", "result"),
    ("Description", lambda e: e.description or "", "description"),
]


def _stream_audit_pdf(entries):
    """Render a PDF of audit-log entries via reportlab.

    Single landscape document with one row per entry, repeating the
    header on each page.  Used by the operator-facing CSV/PDF export
    UI in Reports → Audit Log."""
    import io
    from fastapi.responses import Response
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        title="Audit Log",
        author="SysManage",
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AuditTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=10,
        alignment=1,
    )
    cell_style = ParagraphStyle(
        "AuditCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    )

    headers = [h[0] for h in _PDF_COLUMNS]
    table_data = [headers]
    for entry in entries:
        # Wrap each cell in a Paragraph so long descriptions wrap to
        # multiple lines instead of overflowing the column.
        row = [
            Paragraph(str(getter(entry)), cell_style) for _, getter, _ in _PDF_COLUMNS
        ]
        table_data.append(row)

    flowables = [
        Paragraph(_("Audit Log"), title_style),
        Paragraph(
            f"{_('Generated')}: "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            f"  —  {_('Total Entries')}: {len(entries)}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]

    if not entries:
        flowables.append(Paragraph(_("No audit log entries found."), styles["Normal"]))
    else:
        # Column widths sized for landscape A4 (~770 pt usable width):
        # short columns hold steady, Description gets the slack.
        col_widths = [110, 70, 80, 80, 110, 50, 270]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ]
            )
        )
        flowables.append(table)

    doc.build(flowables)
    buffer.seek(0)
    pdf_bytes = buffer.getvalue()
    filename = f'audit-log-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}.pdf'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
