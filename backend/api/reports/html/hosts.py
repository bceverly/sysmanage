"""
HTML report generators for host-related reports
"""

import json
from datetime import datetime, timezone

from backend.api.error_constants import HTML_BODY_CLOSE, HTML_TABLE_CLOSE
from backend.api.reports.html.common import escape as _escape
from backend.i18n import _


def generate_hosts_html(hosts, report_type: str, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for host reports"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{_escape(report_title)}</title>
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
            <h1>{_escape(report_title)}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_escape(_('Generated'))}:</strong> {_escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
            <p><strong>{_escape(_('Total Hosts'))}:</strong> {_escape(len(hosts))}</p>
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
                        <td>{_escape(hostname)}</td>
                        <td>{_escape(host.fqdn or _('N/A'))}</td>
                        <td>{_escape(ipv4)}</td>
                        <td>{_escape(ipv6)}</td>
                        <td>{_escape(os_name)}</td>
                        <td>{_escape(os_version)}</td>
                        <td>{_escape(host.status or _('unknown'))}</td>
                        <td>{_escape(last_seen)}</td>
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
                        <td>{_escape(hostname)}</td>
                        <td>{_escape(host.fqdn or _('N/A'))}</td>
                        <td>{_escape(host.status or _('unknown'))}</td>
                        <td>{_escape(tags_str)}</td>
                        <td>{_escape(last_seen)}</td>
                    </tr>
                """

        html_content += """
                </tbody>
            </table>
        """

    html_content += HTML_BODY_CLOSE

    return html_content


def generate_firewall_status_html(hosts, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for firewall status report"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{_escape(report_title)}</title>
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
            .port-list {{
                max-width: 200px;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{_escape(report_title)}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_escape(_('Generated'))}:</strong> {_escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
            <p><strong>{_escape(_('Total Hosts'))}:</strong> {_escape(len(hosts))}</p>
        </div>
    """

    if not hosts:
        html_content += f"""
        <div class="no-data">
            <p>{_('No hosts with firewall status found.')}</p>
        </div>
        """
    else:
        html_content += f"""
        <table>
            <thead>
                <tr>
                    <th>{_('Hostname')}</th>
                    <th>{_('IP Address')}</th>
                    <th>{_('OS')}</th>
                    <th>{_('OS Version')}</th>
                    <th>{_('Firewall Software')}</th>
                    <th>{_('IPv4 Ports')}</th>
                    <th>{_('IPv6 Ports')}</th>
                    <th>{_('Status')}</th>
                </tr>
            </thead>
            <tbody>
        """

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

            # Get firewall info from firewall_status relationship
            firewall_name = _("N/A")
            ipv4_ports = _("N/A")
            ipv6_ports = _("N/A")
            firewall_status = _("Unknown")

            if hasattr(host, "firewall_status") and host.firewall_status:
                fw = host.firewall_status
                firewall_name = fw.firewall_name or _("N/A")
                firewall_status = _("Enabled") if fw.enabled else _("Disabled")

                # Format port lists
                if fw.ipv4_ports:
                    try:
                        ports_data = json.loads(fw.ipv4_ports)
                        if ports_data:
                            port_strs = [
                                f"{p.get('port', '')} ({','.join(p.get('protocols', []))})"
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
                                f"{p.get('port', '')} ({','.join(p.get('protocols', []))})"
                                for p in ports_data
                            ]
                            ipv6_ports = ", ".join(port_strs)
                    except (json.JSONDecodeError, AttributeError):
                        ipv6_ports = _("N/A")

            html_content += f"""
                <tr>
                    <td>{_escape(hostname)}</td>
                    <td>{_escape(ip_address)}</td>
                    <td>{_escape(os_name)}</td>
                    <td>{_escape(os_version)}</td>
                    <td>{_escape(firewall_name)}</td>
                    <td class="port-list">{_escape(ipv4_ports)}</td>
                    <td class="port-list">{_escape(ipv6_ports)}</td>
                    <td>{_escape(firewall_status)}</td>
                </tr>
            """

        html_content += HTML_TABLE_CLOSE

    html_content += HTML_BODY_CLOSE

    return html_content


def generate_antivirus_opensource_html(hosts, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for open-source antivirus report"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{_escape(report_title)}</title>
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
            <h1>{_escape(report_title)}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_escape(_('Generated'))}:</strong> {_escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
            <p><strong>{_escape(_('Total Hosts'))}:</strong> {_escape(len(hosts))}</p>
        </div>
    """

    if not hosts:
        html_content += f"""
        <div class="no-data">
            <p>{_('No hosts with open-source antivirus found.')}</p>
        </div>
        """
    else:
        html_content += f"""
        <table>
            <thead>
                <tr>
                    <th>{_('Hostname')}</th>
                    <th>{_('IP Address')}</th>
                    <th>{_('OS')}</th>
                    <th>{_('OS Version')}</th>
                    <th>{_('Antivirus Software')}</th>
                    <th>{_('Version')}</th>
                    <th>{_('Install Path')}</th>
                    <th>{_('Last Updated')}</th>
                    <th>{_('Status')}</th>
                </tr>
            </thead>
            <tbody>
        """

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

            # Get antivirus info from antivirus_status relationship
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
                av_status = _("Enabled") if av.enabled else _("Disabled")

                # Format last_updated
                if av.last_updated:
                    av_last_updated = av.last_updated.strftime("%Y-%m-%d %H:%M")
                else:
                    av_last_updated = _("N/A")

            html_content += f"""
                <tr>
                    <td>{_escape(hostname)}</td>
                    <td>{_escape(ip_address)}</td>
                    <td>{_escape(os_name)}</td>
                    <td>{_escape(os_version)}</td>
                    <td>{_escape(av_name)}</td>
                    <td>{_escape(av_version)}</td>
                    <td>{_escape(av_path)}</td>
                    <td>{_escape(av_last_updated)}</td>
                    <td>{_escape(av_status)}</td>
                </tr>
            """

        html_content += HTML_TABLE_CLOSE

    html_content += HTML_BODY_CLOSE

    return html_content


def generate_antivirus_commercial_html(hosts, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for commercial antivirus report"""

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{_escape(report_title)}</title>
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
            <h1>{_escape(report_title)}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_escape(_('Generated'))}:</strong> {_escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
            <p><strong>{_escape(_('Total Hosts'))}:</strong> {_escape(len(hosts))}</p>
        </div>
    """

    if not hosts:
        html_content += f"""
        <div class="no-data">
            <p>{_('No hosts with commercial antivirus found.')}</p>
        </div>
        """
    else:
        html_content += f"""
        <table>
            <thead>
                <tr>
                    <th>{_('Hostname')}</th>
                    <th>{_('IP Address')}</th>
                    <th>{_('OS')}</th>
                    <th>{_('OS Version')}</th>
                    <th>{_('Product Name')}</th>
                    <th>{_('Product Version')}</th>
                    <th>{_('Signature Version')}</th>
                    <th>{_('Last Updated')}</th>
                    <th>{_('Real-Time Protection')}</th>
                    <th>{_('Service Status')}</th>
                </tr>
            </thead>
            <tbody>
        """

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

                # Format signature_last_updated
                if av.signature_last_updated:
                    signature_last_updated = av.signature_last_updated.strftime(
                        "%Y-%m-%d %H:%M"
                    )
                else:
                    signature_last_updated = _("N/A")

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

            html_content += f"""
                <tr>
                    <td>{_escape(hostname)}</td>
                    <td>{_escape(ip_address)}</td>
                    <td>{_escape(os_name)}</td>
                    <td>{_escape(os_version)}</td>
                    <td>{_escape(product_name)}</td>
                    <td>{_escape(product_version)}</td>
                    <td>{_escape(signature_version)}</td>
                    <td>{_escape(signature_last_updated)}</td>
                    <td>{_escape(realtime_protection)}</td>
                    <td>{_escape(service_status)}</td>
                </tr>
            """

        html_content += HTML_TABLE_CLOSE

    html_content += HTML_BODY_CLOSE

    return html_content
