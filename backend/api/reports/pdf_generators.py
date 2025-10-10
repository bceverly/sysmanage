"""
PDF report generation classes using ReportLab
"""

import io
import json
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.i18n import _
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


class ReportGenerator:
    """Base class for report generation"""

    def __init__(self, db: Session):
        self.db = db
        self.styles = getSampleStyleSheet() if REPORTLAB_AVAILABLE else None

    def create_pdf_buffer(self, title: str, content: List) -> io.BytesIO:
        """Create a PDF document from content list"""
        if not REPORTLAB_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail=_(
                    "PDF generation is not available. Please install reportlab package."
                ),
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
