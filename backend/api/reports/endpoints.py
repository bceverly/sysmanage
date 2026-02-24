"""
Report API endpoints

When the reporting_engine Pro+ module is loaded, these endpoints delegate
to it directly. Otherwise, they return license-required errors.
"""

import html
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.licensing.module_loader import module_loader
from backend.persistence.db import get_db

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


def _check_reporting_module():
    """Check if reporting_engine Pro+ module is available."""
    reporting_engine = module_loader.get_module("reporting_engine")
    if reporting_engine is None:
        raise HTTPException(
            status_code=402,
            detail=_(
                "Report generation requires a SysManage Professional+ license. "
                "Please upgrade to access this feature."
            ),
        )
    return reporting_engine


@router.get("/view/{report_type}")
async def view_report_html(
    report_type: ReportType,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Generate and return HTML version of a report.

    Delegates to reporting_engine Pro+ module when available.
    """
    reporting_engine = _check_reporting_module()

    from backend.persistence import models

    html_gen = reporting_engine.HtmlReportGeneratorImpl(db, _)

    if report_type in (ReportType.REGISTERED_HOSTS, ReportType.HOSTS_WITH_TAGS):
        hosts = db.query(models.Host).order_by(models.Host.fqdn).all()
        report_title = (
            _("Registered Hosts")
            if report_type == ReportType.REGISTERED_HOSTS
            else _("Hosts with Tags")
        )
        html_content = html_gen.generate_hosts_html(
            hosts, report_type.value, report_title
        )
    elif report_type == ReportType.USERS_LIST:
        users = db.query(models.User).order_by(models.User.userid).all()
        html_content = html_gen.generate_users_html(users, _("SysManage Users"))
    elif report_type == ReportType.FIREWALL_STATUS:
        hosts = db.query(models.Host).order_by(models.Host.fqdn).all()
        html_content = html_gen.generate_firewall_html(hosts, _("Host Firewall Status"))
    elif report_type == ReportType.ANTIVIRUS_OPENSOURCE:
        hosts = db.query(models.Host).order_by(models.Host.fqdn).all()
        html_content = html_gen.generate_antivirus_opensource_html(
            hosts, _("Open-Source Antivirus Status")
        )
    elif report_type == ReportType.ANTIVIRUS_COMMERCIAL:
        hosts = db.query(models.Host).order_by(models.Host.fqdn).all()
        html_content = html_gen.generate_antivirus_commercial_html(
            hosts, _("Commercial Antivirus Status")
        )
    elif report_type == ReportType.USER_RBAC:
        users = db.query(models.User).order_by(models.User.userid).all()
        role_groups = (
            db.query(models.SecurityRoleGroup)
            .order_by(models.SecurityRoleGroup.name)
            .all()
        )
        html_content = html_gen.generate_user_rbac_html(
            users, role_groups, _("User Security Roles (RBAC)")
        )
    elif report_type == ReportType.AUDIT_LOG:
        audit_entries = (
            db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).all()
        )
        html_content = html_gen.generate_audit_log_html(audit_entries, _("Audit Log"))
    else:
        raise HTTPException(status_code=400, detail=_("Unknown report type"))

    # nosemgrep: python.fastapi.web.tainted-direct-response-fastapi - html_content is generated
    # by a trusted Pro+ reporting module from enum-validated report types and ORM-fetched data
    return HTMLResponse(content=html_content)


@router.get("/generate/{report_type}")
async def generate_report(
    report_type: ReportType,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Generate and download a PDF report.

    Delegates to reporting_engine Pro+ module when available.
    """
    reporting_engine = _check_reporting_module()

    from backend.persistence import models

    hosts_gen = reporting_engine.HostsReportGeneratorImpl(db, i18n_func=_)
    users_gen = reporting_engine.UsersReportGeneratorImpl(db, i18n_func=_)

    if not hosts_gen.reportlab_available:
        raise HTTPException(
            status_code=500,
            detail=_(
                "PDF generation is not available. Please install reportlab package."
            ),
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if report_type == ReportType.REGISTERED_HOSTS:
        pdf_buffer = hosts_gen.generate_hosts_report(models)
        filename = f"registered_hosts_{ts}.pdf"
    elif report_type == ReportType.HOSTS_WITH_TAGS:
        pdf_buffer = hosts_gen.generate_hosts_with_tags_report(models)
        filename = f"hosts_with_tags_{ts}.pdf"
    elif report_type == ReportType.USERS_LIST:
        pdf_buffer = users_gen.generate_users_list_report(models)
        filename = f"users_list_{ts}.pdf"
    elif report_type == ReportType.FIREWALL_STATUS:
        pdf_buffer = hosts_gen.generate_firewall_status_report(models)
        filename = f"firewall_status_{ts}.pdf"
    elif report_type == ReportType.ANTIVIRUS_OPENSOURCE:
        pdf_buffer = hosts_gen.generate_antivirus_opensource_report(models)
        filename = f"antivirus_opensource_{ts}.pdf"
    elif report_type == ReportType.ANTIVIRUS_COMMERCIAL:
        pdf_buffer = hosts_gen.generate_antivirus_commercial_report(models)
        filename = f"antivirus_commercial_{ts}.pdf"
    elif report_type == ReportType.USER_RBAC:
        pdf_buffer = users_gen.generate_user_rbac_report(models)
        filename = f"user_rbac_{ts}.pdf"
    elif report_type == ReportType.AUDIT_LOG:
        pdf_buffer = hosts_gen.generate_audit_log_report(models)
        filename = f"audit_log_{ts}.pdf"
    else:
        raise HTTPException(status_code=400, detail=_("Unknown report type"))

    pdf_bytes = pdf_buffer.getvalue()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/screenshots/{report_id}")
@router.head("/screenshots/{report_id}")
@router.options("/screenshots/{report_id}")
async def get_report_screenshot(report_id: str):
    """
    Serve report screenshots for the UI cards.

    This endpoint remains available to show placeholder images.
    """
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
