"""
Report API endpoints
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, sessionmaker

from backend.api.reports.html_generators import generate_hosts_html, generate_users_html
from backend.api.reports.pdf_generators import (
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


@router.get("/view/{report_type}")
async def view_report_html(
    report_type: str,
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

        if report_type == "registered-hosts":
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Registered Hosts")

        elif report_type == "hosts-with-tags":
            hosts = db.query(Host).order_by(Host.fqdn).all()
            report_title = _("Hosts with Tags")

        elif report_type == "users-list":
            users = db.query(User).order_by(User.userid).all()
            report_title = _("SysManage Users")

        else:
            raise HTTPException(
                status_code=400,
                detail=_("Invalid report type: {report_type}").format(
                    report_type=report_type
                ),
            )

        # Generate HTML content based on report type
        if report_type in ["registered-hosts", "hosts-with-tags"]:
            html_content = generate_hosts_html(hosts, report_type, report_title)
        else:
            html_content = generate_users_html(users, report_title)

        return Response(content=html_content, media_type="text/html")

    except HTTPException:
        # Re-raise HTTP exceptions (like 400 errors) without modification
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_("Internal server error")) from e


@router.get("/generate/{report_type}")
async def generate_report(
    report_type: str,
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
        if report_type == "registered-hosts":
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_hosts_report()
            filename = f"registered_hosts_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == "hosts-with-tags":
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_hosts_with_tags_report()
            filename = f"hosts_with_tags_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == "users-list":
            generator = UsersReportGenerator(db)
            pdf_buffer = generator.generate_users_list_report()
            filename = (
                f"users_list_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
            )

        else:
            raise HTTPException(
                status_code=404,
                detail=_("Report type '{report_type}' not found").format(
                    report_type=report_type
                ),
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
            {report_id.replace('-', ' ').title()} {_('Report')}
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
