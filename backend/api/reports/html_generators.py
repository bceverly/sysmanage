"""
HTML report generation functions
"""

import json
from datetime import datetime, timezone

from backend.i18n import _


def generate_hosts_html(hosts, report_type: str, report_title: str) -> str:
    """Generate HTML content for host reports"""

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
