"""
Reports API endpoints for generating PDF reports
"""

import io
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from backend.auth.auth_bearer import get_current_user
from backend.i18n import _
from backend.persistence.db import get_db
from backend.persistence.models import Host, User

# PDF generation imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

router = APIRouter(prefix="/api/reports", tags=["reports"])


def generate_hosts_html(hosts, report_type: str, report_title: str) -> str:
    """Generate HTML content for host reports"""
    import json

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{report_title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .header {{
                background-color: #1976d2;
                color: white;
                padding: 20px;
                text-align: center;
                margin-bottom: 20px;
                border-radius: 8px;
            }}
            .metadata {{
                background-color: white;
                padding: 15px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            table {{
                width: 100%;
                background-color: white;
                border-collapse: collapse;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th {{
                background-color: #666;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: bold;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #ddd;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .no-data {{
                text-align: center;
                padding: 40px;
                color: #666;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{report_title}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_('Generated')}:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p><strong>{_('Total Hosts')}:</strong> {len(hosts)}</p>
        </div>
    """

    if not hosts:
        html_content += f"""
        <div class="no-data">
            <p>{_('No hosts are currently registered in the system.')}</p>
        </div>
        """
    else:
        if report_type in ["registered-hosts", "hosts"]:
            html_content += f"""
            <table>
                <thead>
                    <tr>
                        <th>{_('Hostname')}</th>
                        <th>{_('FQDN')}</th>
                        <th>{_('IPv4')}</th>
                        <th>{_('IPv6')}</th>
                        <th>{_('OS')}</th>
                        <th>{_('Version')}</th>
                        <th>{_('Status')}</th>
                        <th>{_('Last Seen')}</th>
                    </tr>
                </thead>
                <tbody>
            """

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Format IPs
                ipv4 = host.ipv4 or _("N/A")
                ipv6 = host.ipv6 or _("N/A")
                if ipv6 != _("N/A") and len(ipv6) > 20:
                    ipv6 = ipv6[:20] + "..."

                # Extract OS info from JSON
                os_name = _("N/A")
                os_version = _("N/A")
                if host.os_details:
                    try:
                        os_data = json.loads(host.os_details)
                        os_name = os_data.get("distribution", host.platform or _("N/A"))
                        os_version = os_data.get(
                            "distribution_version", host.platform_release or _("N/A")
                        )
                    except (json.JSONDecodeError, AttributeError):
                        os_name = host.platform or _("N/A")
                        os_version = host.platform_release or _("N/A")
                else:
                    os_name = host.platform or _("N/A")
                    os_version = host.platform_release or _("N/A")

                # Format last access
                last_seen = (
                    host.last_access.strftime("%Y-%m-%d %H:%M")
                    if host.last_access
                    else _("Never")
                )

                html_content += f"""
                    <tr>
                        <td>{hostname}</td>
                        <td>{host.fqdn or _('N/A')}</td>
                        <td>{ipv4}</td>
                        <td>{ipv6}</td>
                        <td>{os_name}</td>
                        <td>{os_version}</td>
                        <td>{host.status or _('unknown')}</td>
                        <td>{last_seen}</td>
                    </tr>
                """
        else:  # hosts-with-tags
            html_content += f"""
            <table>
                <thead>
                    <tr>
                        <th>{_('Hostname')}</th>
                        <th>{_('FQDN')}</th>
                        <th>{_('Status')}</th>
                        <th>{_('Tags')}</th>
                        <th>{_('Last Seen')}</th>
                    </tr>
                </thead>
                <tbody>
            """

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Get tags for this host
                tags = [tag.name for tag in host.tags] if host.tags else []
                tags_str = ", ".join(tags) if tags else _("No tags")

                # Format last access
                last_seen = (
                    host.last_access.strftime("%Y-%m-%d %H:%M")
                    if host.last_access
                    else _("Never")
                )

                html_content += f"""
                    <tr>
                        <td>{hostname}</td>
                        <td>{host.fqdn or _('N/A')}</td>
                        <td>{host.status or _('unknown')}</td>
                        <td>{tags_str}</td>
                        <td>{last_seen}</td>
                    </tr>
                """

        html_content += """
                </tbody>
            </table>
        """

    html_content += """
    </body>
    </html>
    """

    return html_content


def generate_users_html(users, report_title: str) -> str:
    """Generate HTML content for user reports"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{report_title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .header {{
                background-color: #1976d2;
                color: white;
                padding: 20px;
                text-align: center;
                margin-bottom: 20px;
                border-radius: 8px;
            }}
            .metadata {{
                background-color: white;
                padding: 15px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            table {{
                width: 100%;
                background-color: white;
                border-collapse: collapse;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            th {{
                background-color: #666;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: bold;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #ddd;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .no-data {{
                text-align: center;
                padding: 40px;
                color: #666;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{report_title}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_('Generated')}:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p><strong>{_('Total Users')}:</strong> {len(users)}</p>
        </div>
    """

    if not users:
        html_content += f"""
        <div class="no-data">
            <p>{_('No users are currently registered in the system.')}</p>
        </div>
        """
    else:
        html_content += f"""
        <table>
            <thead>
                <tr>
                    <th>{_('User ID')}</th>
                    <th>{_('First Name')}</th>
                    <th>{_('Last Name')}</th>
                    <th>{_('Status')}</th>
                    <th>{_('Last Access')}</th>
                    <th>{_('Account Security')}</th>
                </tr>
            </thead>
            <tbody>
        """

        for user in users:
            # Format last access
            last_access = (
                user.last_access.strftime("%Y-%m-%d %H:%M")
                if user.last_access
                else _("Never")
            )

            # Determine status
            status = _("Active") if user.active else _("Inactive")

            # Account security status
            security_status = _("Locked") if user.is_locked else _("Normal")
            if user.failed_login_attempts > 0:
                security_status += (
                    " ("
                    + _("{n} failed attempts").format(n=user.failed_login_attempts)
                    + ")"
                )

            html_content += f"""
                <tr>
                    <td>{user.userid or _('N/A')}</td>
                    <td>{user.first_name or _('N/A')}</td>
                    <td>{user.last_name or _('N/A')}</td>
                    <td>{status}</td>
                    <td>{last_access}</td>
                    <td>{security_status}</td>
                </tr>
            """

        html_content += """
            </tbody>
        </table>
        """

    html_content += """
    </body>
    </html>
    """

    return html_content


class ReportGenerator:
    """Base class for report generation"""

    def __init__(self, db: Session):
        self.db = db
        self.styles = getSampleStyleSheet() if REPORTLAB_AVAILABLE else None

    def create_pdf_buffer(self, title: str, content: List) -> io.BytesIO:
        """Create a PDF document from content list"""
        if not REPORTLAB_AVAILABLE:
            raise HTTPException(
                status_code=500, detail=_("PDF generation not available")
            )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=title,
            author="SysManage",
            subject=title,
            creator="SysManage Reporting System",
        )

        # Build the document
        doc.build(content)
        buffer.seek(0)
        return buffer


class HostsReportGenerator(ReportGenerator):
    """Generator for host-related reports"""

    def generate_hosts_report(self) -> io.BytesIO:
        """Generate registered hosts report with basic and OS information"""
        hosts = self.db.query(Host).order_by(Host.fqdn).all()

        content = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=18,
            spaceAfter=30,
            alignment=1,  # Center alignment
        )
        content.append(Paragraph(_("Registered Hosts"), title_style))
        content.append(Spacer(1, 20))

        # Report metadata
        metadata_style = self.styles["Normal"]
        content.append(
            Paragraph(
                f"{_('Generated')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                metadata_style,
            )
        )
        content.append(Paragraph(f"{_('Total Hosts')}: {len(hosts)}", metadata_style))
        content.append(Spacer(1, 20))

        if not hosts:
            content.append(
                Paragraph(
                    _("No hosts are currently registered in the system."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("Hostname"),
                    _("FQDN"),
                    _("IPv4"),
                    _("IPv6"),
                    _("OS"),
                    _("Version"),
                    _("Status"),
                    _("Last Seen"),
                ]
            ]

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Format IPs
                ipv4 = host.ipv4 or _("N/A")
                ipv6 = host.ipv6 or _("N/A")
                if ipv6 != _("N/A") and len(ipv6) > 20:
                    ipv6 = ipv6[:20] + "..."  # Truncate long IPv6

                # Extract OS info from JSON
                import json

                os_name = _("N/A")
                os_version = _("N/A")
                if host.os_details:
                    try:
                        os_data = json.loads(host.os_details)
                        os_name = os_data.get("distribution", host.platform or _("N/A"))
                        os_version = os_data.get(
                            "distribution_version", host.platform_release or _("N/A")
                        )
                    except (json.JSONDecodeError, AttributeError):
                        os_name = host.platform or _("N/A")
                        os_version = host.platform_release or _("N/A")
                else:
                    os_name = host.platform or _("N/A")
                    os_version = host.platform_release or _("N/A")

                # Format last access
                last_seen = (
                    host.last_access.strftime("%Y-%m-%d %H:%M")
                    if host.last_access
                    else _("Never")
                )

                table_data.append(
                    [
                        hostname,
                        host.fqdn or _("N/A"),
                        ipv4,
                        ipv6,
                        os_name,
                        os_version,
                        host.status or _("unknown"),
                        last_seen,
                    ]
                )

            # Create table
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("Registered Hosts"), content)

    def generate_hosts_with_tags_report(self) -> io.BytesIO:
        """Generate hosts with tags report"""
        hosts = self.db.query(Host).order_by(Host.fqdn).all()

        content = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=18,
            spaceAfter=30,
            alignment=1,
        )
        content.append(Paragraph(_("Hosts with Tags"), title_style))
        content.append(Spacer(1, 20))

        # Report metadata
        metadata_style = self.styles["Normal"]
        content.append(
            Paragraph(
                f"{_('Generated')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                metadata_style,
            )
        )
        content.append(Paragraph(f"{_('Total Hosts')}: {len(hosts)}", metadata_style))
        content.append(Spacer(1, 20))

        if not hosts:
            content.append(
                Paragraph(
                    _("No hosts are currently registered in the system."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [_("Hostname"), _("FQDN"), _("Status"), _("Tags"), _("Last Seen")]
            ]

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Get tags for this host
                tags = [tag.name for tag in host.tags] if host.tags else []
                tags_str = ", ".join(tags) if tags else _("No tags")

                # Format last access
                last_seen = (
                    host.last_access.strftime("%Y-%m-%d %H:%M")
                    if host.last_access
                    else _("Never")
                )

                table_data.append(
                    [
                        hostname,
                        host.fqdn or _("N/A"),
                        host.status or _("unknown"),
                        tags_str,
                        last_seen,
                    ]
                )

            # Create table
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("Hosts with Tags"), content)


class UsersReportGenerator(ReportGenerator):
    """Generator for user-related reports"""

    def generate_users_list_report(self) -> io.BytesIO:
        """Generate SysManage users list report"""
        users = self.db.query(User).order_by(User.userid).all()

        content = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=18,
            spaceAfter=30,
            alignment=1,
        )
        content.append(Paragraph(_("SysManage Users"), title_style))
        content.append(Spacer(1, 20))

        # Report metadata
        metadata_style = self.styles["Normal"]
        content.append(
            Paragraph(
                f"{_('Generated')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                metadata_style,
            )
        )
        content.append(Paragraph(f"{_('Total Users')}: {len(users)}", metadata_style))
        content.append(Spacer(1, 20))

        if not users:
            content.append(
                Paragraph(
                    _("No users are currently registered in the system."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("User ID"),
                    _("First Name"),
                    _("Last Name"),
                    _("Status"),
                    _("Last Access"),
                    _("Account Security"),
                ]
            ]

            for user in users:
                # Combine first and last name
                full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not full_name:
                    full_name = _("N/A")

                # Format last access
                last_access = (
                    user.last_access.strftime("%Y-%m-%d %H:%M")
                    if user.last_access
                    else _("Never")
                )

                # Determine status
                status = _("Active") if user.active else _("Inactive")

                # Account security status
                security_status = _("Locked") if user.is_locked else _("Normal")
                if user.failed_login_attempts > 0:
                    security_status += (
                        " ("
                        + _("{n} failed attempts").format(n=user.failed_login_attempts)
                        + ")"
                    )

                table_data.append(
                    [
                        user.userid or _("N/A"),
                        user.first_name or _("N/A"),
                        user.last_name or _("N/A"),
                        status,
                        last_access,
                        security_status,
                    ]
                )

            # Create table
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("SysManage Users"), content)


@router.get("/view/{report_type}")
async def view_report_html(
    report_type: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate and return HTML version of a report
    """
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
            filename = (
                f"registered_hosts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )

        elif report_type == "hosts-with-tags":
            generator = HostsReportGenerator(db)
            pdf_buffer = generator.generate_hosts_with_tags_report()
            filename = f"hosts_with_tags_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        elif report_type == "users-list":
            generator = UsersReportGenerator(db)
            pdf_buffer = generator.generate_users_list_report()
            filename = f"users_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

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
