"""
Report API endpoints
"""

import html
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, sessionmaker

from backend.api.reports.html import (
    generate_antivirus_commercial_html,
    generate_antivirus_opensource_html,
    generate_audit_log_html,
    generate_firewall_status_html,
    generate_hosts_html,
    generate_user_rbac_html,
    generate_users_html,
)
from backend.api.reports.pdf import (
    REPORTLAB_AVAILABLE,
    HostsReportGenerator,
    UsersReportGenerator,
)
from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence import models
from backend.persistence.db import get_db
from backend.persistence.models import Host, User
from backend.security.roles import SecurityRoles

router = APIRouter(prefix="/api/reports", tags=["reports"])


# Define allowed report types to prevent injection
class ReportType(str, Enum):
    """Valid report types"""

    REGISTERED_HOSTS = "registered-hosts"
    HOSTS_WITH_TAGS = "hosts-with-tags"
    USERS_LIST = "users-list"
    FIREWALL_STATUS = "firewall-status"
    ANTIVIRUS_OPENSOURCE = "antivirus-opensource"
    ANTIVIRUS_COMMERCIAL = "antivirus-commercial"
    USER_RBAC = "user-rbac"
    AUDIT_LOG = "audit-log"


@router.get("/view/{report_type}", response_class=HTMLResponse)
async def view_report_html(  # NOSONAR
    report_type: ReportType,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate and return HTML version of a report
    """
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    with session_local() as session:
        # Check if user has permission to view reports
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.VIEW_REPORT):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: VIEW_REPORT role required"),
            )

    try:
        hosts = None
        users = None
        audit_entries = None
        report_title = ""

        # report_type is validated by FastAPI Enum, so only valid values are allowed
        if report_type == ReportType.REGISTERED_HOSTS:
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Registered Hosts")

        elif report_type == ReportType.HOSTS_WITH_TAGS:
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Hosts with Tags")

        elif report_type == ReportType.USERS_LIST:
            users = db.query(User).order_by(User.userid).all()
            report_title = _("SysManage Users")

        elif report_type == ReportType.FIREWALL_STATUS:
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Host Firewall Status")

        elif report_type == ReportType.ANTIVIRUS_OPENSOURCE:
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Open-Source Antivirus Status")

        elif report_type == ReportType.ANTIVIRUS_COMMERCIAL:
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Commercial Antivirus Status")

        elif report_type == ReportType.USER_RBAC:
            users = db.query(User).order_by(User.userid).all()
            report_title = _("User Security Roles (RBAC)")

        elif report_type == ReportType.AUDIT_LOG:
            from backend.persistence.models import AuditLog

            audit_entries = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
            report_title = _("Audit Log")

        # Generate HTML content based on report type
        # All user input is properly escaped using html.escape() in html_generators.py
        # The _escape() function is applied to all dynamic content to prevent XSS.
        if report_type in [ReportType.REGISTERED_HOSTS, ReportType.HOSTS_WITH_TAGS]:
            html_content = generate_hosts_html(hosts, report_type.value, report_title)
        elif report_type == ReportType.USERS_LIST:
            html_content = generate_users_html(users, report_title)
        elif report_type == ReportType.FIREWALL_STATUS:
            html_content = generate_firewall_status_html(hosts, report_title)
        elif report_type == ReportType.ANTIVIRUS_OPENSOURCE:
            html_content = generate_antivirus_opensource_html(hosts, report_title)
        elif report_type == ReportType.ANTIVIRUS_COMMERCIAL:
            html_content = generate_antivirus_commercial_html(hosts, report_title)
        elif report_type == ReportType.AUDIT_LOG:
            html_content = generate_audit_log_html(audit_entries, report_title)
        else:  # USER_RBAC
            html_content = generate_user_rbac_html(db, users, report_title)

        # Use HTMLResponse which is the proper FastAPI way to return HTML
        # Input validation via Enum + HTML escaping in generators = XSS protection
        # nosemgrep: python.fastapi.web.tainted-direct-response-fastapi.tainted-direct-response-fastapi, tainted-direct-response-fastapi
        return HTMLResponse(content=html_content)

    except HTTPException:
        # Re-raise HTTP exceptions (like 400 errors) without modification
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e


@router.get("/generate/{report_type}")
async def generate_report(
    report_type: ReportType,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate and download a PDF report
    """
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    with session_local() as session:
        # Check if user has permission to generate PDF reports
        auth_user = (
            session.query(models.User)
            .filter(models.User.userid == current_user)
            .first()
        )
        if not auth_user:
            raise HTTPException(status_code=401, detail=_("User not found"))
        if auth_user._role_cache is None:
            auth_user.load_role_cache(session)
        if not auth_user.has_role(SecurityRoles.GENERATE_PDF_REPORT):
            raise HTTPException(
                status_code=403,
                detail=_("Permission denied: GENERATE_PDF_REPORT role required"),
            )

    if not REPORTLAB_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=_(
                "PDF generation is not available. Please install reportlab package."
            ),
        )

    try:
        # report_type is validated by FastAPI Enum, so only valid values are allowed
        if report_type == ReportType.REGISTERED_HOSTS:
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_hosts_report()
            filename = f"registered_hosts_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == ReportType.HOSTS_WITH_TAGS:
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_hosts_with_tags_report()
            filename = f"hosts_with_tags_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == ReportType.USERS_LIST:
            generator = UsersReportGenerator(db)
            pdf_buffer = generator.generate_users_list_report()
            filename = (
                f"users_list_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
            )

        elif report_type == ReportType.FIREWALL_STATUS:
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_firewall_status_report()
            filename = f"firewall_status_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == ReportType.ANTIVIRUS_OPENSOURCE:
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_antivirus_opensource_report()
            filename = f"antivirus_opensource_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == ReportType.ANTIVIRUS_COMMERCIAL:
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_antivirus_commercial_report()
            filename = f"antivirus_commercial_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == ReportType.USER_RBAC:
            generator = UsersReportGenerator(db)
            pdf_buffer = generator.generate_user_rbac_report()
            filename = (
                f"user_rbac_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
            )

        else:  # ReportType.AUDIT_LOG
            generator = UsersReportGenerator(db)
            pdf_buffer = generator.generate_audit_log_report()
            filename = (
                f"audit_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
            )

        # Return the PDF as response
        return Response(
            content=pdf_buffer.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        # Re-raise HTTP exceptions (like 404 errors) without modification
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=_("Error generating PDF report")
        ) from e


@router.get("/screenshots/{report_id}")
@router.head("/screenshots/{report_id}")
@router.options("/screenshots/{report_id}")
async def get_report_screenshot(report_id: str):
    """
    Serve report screenshots for the UI cards
    """
    # In a real implementation, you might store actual screenshots
    # For now, return a placeholder SVG
    # Escape report_id to prevent XSS attacks
    escaped_report_title = html.escape(report_id.replace("-", " ").title())
    escaped_report_label = html.escape(_("Report"))
    placeholder_svg = f"""
    <svg width="300" height="200" viewBox="0 0 300 200" xmlns="http://www.w3.org/2000/svg">
        <rect width="300" height="200" fill="#374151"/>
        <rect x="20" y="20" width="260" height="160" fill="#4A5568"/>
        <rect x="30" y="40" width="240" height="20" fill="#6B7280"/>
        <rect x="30" y="70" width="200" height="15" fill="#6B7280"/>
        <rect x="30" y="90" width="180" height="15" fill="#6B7280"/>
        <rect x="30" y="110" width="220" height="15" fill="#6B7280"/>
        <rect x="30" y="130" width="160" height="15" fill="#6B7280"/>
        <text x="150" y="170" text-anchor="middle" fill="#9CA3AF" font-family="Arial" font-size="12">
            {escaped_report_title} {escaped_report_label}
        </text>
    </svg>
    """

    return Response(
        content=placeholder_svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Length": str(len(placeholder_svg.encode("utf-8"))),
        },
    )


# Export the router
__all__ = ["router"]
