"""
PDF report generator for host-related reports
"""

import io
import json
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from backend.api.reports.pdf.base import ReportGenerator
from backend.i18n import _
from backend.persistence.models import Host


class HostsReportGenerator(ReportGenerator):
    """Generator for host-related reports"""

    def generate_hosts_report(self) -> io.BytesIO:  # NOSONAR
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

    def generate_hosts_with_tags_report(  # NOSONAR
        self,
    ) -> io.BytesIO:
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

    def generate_firewall_status_report(  # NOSONAR
        self,
    ) -> io.BytesIO:
        """Generate firewall status report for all hosts"""
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
        content.append(Paragraph(_("Host Firewall Status"), title_style))
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
                    _("No hosts with firewall status found."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("Hostname"),
                    _("IP Address"),
                    _("OS"),
                    _("OS Version"),
                    _("Firewall Software"),
                    _("IPv4 Ports"),
                    _("IPv6 Ports"),
                    _("Status"),
                ]
            ]

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Get IP address (prefer IPv4)
                ip_address = host.ipv4 or host.ipv6 or _("N/A")

                # Extract OS info
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

                # Get firewall info
                firewall_name = _("N/A")
                ipv4_ports = _("N/A")
                ipv6_ports = _("N/A")
                firewall_status = _("Unknown")

                if hasattr(host, "firewall_status") and host.firewall_status:
                    fw = host.firewall_status
                    firewall_name = fw.firewall_name or _("N/A")
                    firewall_status = _("Enabled") if fw.enabled else _("Disabled")

                    # Format port lists (show all ports)
                    if fw.ipv4_ports:
                        try:
                            ports_data = json.loads(fw.ipv4_ports)
                            if ports_data:
                                port_strs = [
                                    f"{p.get('port', '')}({','.join(p.get('protocols', []))})"
                                    for p in ports_data
                                ]
                                ipv4_ports = ", ".join(port_strs)
                        except (json.JSONDecodeError, AttributeError):
                            ipv4_ports = _("N/A")

                    if fw.ipv6_ports:
                        try:
                            ports_data = json.loads(fw.ipv6_ports)
                            if ports_data:
                                port_strs = [
                                    f"{p.get('port', '')}({','.join(p.get('protocols', []))})"
                                    for p in ports_data
                                ]
                                ipv6_ports = ", ".join(port_strs)
                        except (json.JSONDecodeError, AttributeError):
                            ipv6_ports = _("N/A")

                table_data.append(
                    [
                        hostname,
                        ip_address,
                        os_name,
                        os_version,
                        firewall_name,
                        ipv4_ports,
                        ipv6_ports,
                        firewall_status,
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
                        ("FONTSIZE", (0, 0), (-1, 0), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 7),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("Host Firewall Status"), content)

    def generate_antivirus_opensource_report(  # NOSONAR
        self,
    ) -> io.BytesIO:
        """Generate open-source antivirus status report for all hosts"""
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
        content.append(Paragraph(_("Open-Source Antivirus Status"), title_style))
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
                    _("No hosts with open-source antivirus found."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("Hostname"),
                    _("IP Address"),
                    _("OS"),
                    _("OS Version"),
                    _("Antivirus Software"),
                    _("Version"),
                    _("Install Path"),
                    _("Last Updated"),
                    _("Status"),
                ]
            ]

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Get IP address (prefer IPv4)
                ip_address = host.ipv4 or host.ipv6 or _("N/A")

                # Extract OS info
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

                # Get antivirus info
                av_name = _("N/A")
                av_version = _("N/A")
                av_path = _("N/A")
                av_last_updated = _("N/A")
                av_status = _("Unknown")

                if hasattr(host, "antivirus_status") and host.antivirus_status:
                    av = host.antivirus_status
                    av_name = av.software_name or _("N/A")
                    av_version = av.version or _("N/A")
                    av_path = av.install_path or _("N/A")
                    # Truncate long paths
                    if len(av_path) > 30:
                        av_path = av_path[:30] + "..."
                    # Format last updated
                    if av.last_updated:
                        av_last_updated = av.last_updated.strftime("%Y-%m-%d %H:%M")
                    av_status = _("Enabled") if av.enabled else _("Disabled")

                table_data.append(
                    [
                        hostname,
                        ip_address,
                        os_name,
                        os_version,
                        av_name,
                        av_version,
                        av_path,
                        av_last_updated,
                        av_status,
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
                        ("FONTSIZE", (0, 0), (-1, 0), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 7),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("Open-Source Antivirus Status"), content)

    def generate_antivirus_commercial_report(  # NOSONAR
        self,
    ) -> io.BytesIO:
        """Generate commercial antivirus status report for all hosts"""
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
        content.append(Paragraph(_("Commercial Antivirus Status"), title_style))
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
                    _("No hosts with commercial antivirus found."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("Hostname"),
                    _("IP Address"),
                    _("OS"),
                    _("OS Version"),
                    _("Product Name"),
                    _("Product Version"),
                    _("Signature Version"),
                    _("Last Updated"),
                    _("Real-Time Protection"),
                    _("Service Status"),
                ]
            ]

            for host in hosts:
                # Extract hostname from FQDN
                hostname = host.fqdn.split(".")[0] if host.fqdn else _("N/A")

                # Get IP address (prefer IPv4)
                ip_address = host.ipv4 or host.ipv6 or _("N/A")

                # Extract OS info
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

                # Get commercial antivirus info
                product_name = _("N/A")
                product_version = _("N/A")
                signature_version = _("N/A")
                signature_last_updated = _("N/A")
                realtime_protection = _("Unknown")
                service_status = _("Unknown")

                if (
                    hasattr(host, "commercial_antivirus_status")
                    and host.commercial_antivirus_status
                ):
                    av = host.commercial_antivirus_status
                    product_name = av.product_name or _("N/A")
                    product_version = av.product_version or _("N/A")
                    signature_version = av.signature_version or _("N/A")

                    # Format signature last updated
                    if av.signature_last_updated:
                        signature_last_updated = av.signature_last_updated.strftime(
                            "%Y-%m-%d %H:%M"
                        )

                    if av.realtime_protection_enabled is not None:
                        realtime_protection = (
                            _("Enabled")
                            if av.realtime_protection_enabled
                            else _("Disabled")
                        )

                    if av.service_enabled is not None:
                        service_status = (
                            _("Enabled") if av.service_enabled else _("Disabled")
                        )

                table_data.append(
                    [
                        hostname,
                        ip_address,
                        os_name,
                        os_version,
                        product_name,
                        product_version,
                        signature_version,
                        signature_last_updated,
                        realtime_protection,
                        service_status,
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
                        ("FONTSIZE", (0, 0), (-1, 0), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            content.append(table)

        return self.create_pdf_buffer(_("Commercial Antivirus Status"), content)
