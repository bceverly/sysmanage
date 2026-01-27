"""
HTML report generators for user-related reports
"""

import json
from datetime import datetime, timezone

from backend.api.error_constants import HTML_BODY_CLOSE
from backend.api.reports.html.common import escape as _escape
from backend.i18n import _


def generate_users_html(users, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for user reports"""

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
            <p><strong>{_escape(_('Total Users'))}:</strong> {_escape(len(users))}</p>
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
                    <td>{_escape(user.userid or _('N/A'))}</td>
                    <td>{_escape(user.first_name or _('N/A'))}</td>
                    <td>{_escape(user.last_name or _('N/A'))}</td>
                    <td>{_escape(status)}</td>
                    <td>{_escape(last_access)}</td>
                    <td>{_escape(security_status)}</td>
                </tr>
            """

        html_content += """
            </tbody>
        </table>
        """

    html_content += HTML_BODY_CLOSE

    return html_content


def generate_user_rbac_html(db, users, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for user RBAC report showing roles grouped by role groups"""
    from backend.persistence.models import SecurityRole, SecurityRoleGroup

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
            .user-section {{
                background-color: white;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            .user-header {{
                background-color: #2196f3;
                color: white;
                padding: 15px;
                font-weight: bold;
                font-size: 16px;
            }}
            .role-group {{
                padding: 15px;
                border-bottom: 1px solid #e0e0e0;
            }}
            .role-group:last-child {{
                border-bottom: none;
            }}
            .role-group-title {{
                font-weight: bold;
                color: #333;
                margin-bottom: 8px;
                font-size: 14px;
            }}
            .roles-list {{
                margin-left: 20px;
                color: #555;
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                column-gap: 20px;
                row-gap: 4px;
            }}
            .role-item {{
                padding: 4px 0;
            }}
            .no-roles {{
                color: #999;
                font-style: italic;
                margin-left: 20px;
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
            <p><strong>{_escape(_('Total Users'))}:</strong> {_escape(len(users))}</p>
        </div>
    """

    if not users:
        html_content += f"""
        <div class="no-data">
            <p>{_('No users are currently registered in the system.')}</p>
        </div>
        """
    else:
        # Get all role groups for organization
        role_groups = db.query(SecurityRoleGroup).order_by(SecurityRoleGroup.name).all()

        for user in users:
            # Get user's full name
            user_display_name = user.userid
            if user.first_name or user.last_name:
                name_parts = []
                if user.first_name:
                    name_parts.append(user.first_name)
                if user.last_name:
                    name_parts.append(user.last_name)
                user_display_name += f" ({' '.join(name_parts)})"

            html_content += f"""
            <div class="user-section">
                <div class="user-header">{_escape(user_display_name)}</div>
            """

            # Get all roles for this user
            user_roles = list(user.security_roles)

            if not user_roles:
                html_content += f"""
                <div class="role-group">
                    <div class="no-roles">{_('No security roles assigned')}</div>
                </div>
                """
            else:
                # Group roles by their role group
                for group in role_groups:
                    # Get roles in this group that the user has
                    group_roles = [
                        role for role in user_roles if role.group_id == group.id
                    ]

                    if group_roles:
                        html_content += f"""
                        <div class="role-group">
                            <div class="role-group-title">{_escape(group.name)}</div>
                            <div class="roles-list">
                        """

                        for role in sorted(group_roles, key=lambda r: r.name):
                            html_content += f"""
                                <div class="role-item">• {_escape(role.name)}</div>
                            """

                        html_content += """
                            </div>
                        </div>
                        """

            html_content += """
            </div>
            """

    html_content += HTML_BODY_CLOSE

    return html_content


def generate_audit_log_html(audit_entries, report_title: str) -> str:  # NOSONAR
    """Generate HTML content for audit log report"""

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
            .result-success {{
                color: #4caf50;
                font-weight: bold;
            }}
            .result-failure {{
                color: #f44336;
                font-weight: bold;
            }}
            .result-pending {{
                color: #ff9800;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{_escape(report_title)}</h1>
        </div>

        <div class="metadata">
            <p><strong>{_escape(_('Generated'))}:</strong> {_escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))}</p>
            <p><strong>{_escape(_('Total Entries'))}:</strong> {_escape(len(audit_entries))}</p>
        </div>
    """

    if not audit_entries:
        html_content += f"""
        <div class="no-data">
            <p>{_('No audit log entries found.')}</p>
        </div>
        """
    else:
        html_content += f"""
        <table>
            <thead>
                <tr>
                    <th>{_('Timestamp')}</th>
                    <th>{_('User')}</th>
                    <th>{_('Action')}</th>
                    <th>{_('Entity Type')}</th>
                    <th>{_('Entity Name')}</th>
                    <th>{_('Result')}</th>
                    <th>{_('Description')}</th>
                </tr>
            </thead>
            <tbody>
        """

        for entry in audit_entries:
            # Format timestamp
            timestamp_str = (
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if entry.timestamp
                else _("N/A")
            )

            # Get username or system
            username = entry.username if entry.username else _("System")

            # Get result class for styling
            result_class = ""
            if entry.result == "SUCCESS":
                result_class = "result-success"
            elif entry.result == "FAILURE":
                result_class = "result-failure"
            elif entry.result == "PENDING":
                result_class = "result-pending"

            html_content += f"""
                <tr>
                    <td>{_escape(timestamp_str)}</td>
                    <td>{_escape(username)}</td>
                    <td>{_escape(entry.action_type or _('N/A'))}</td>
                    <td>{_escape(entry.entity_type or _('N/A'))}</td>
                    <td>{_escape(entry.entity_name or _('N/A'))}</td>
                    <td class="{result_class}">{_escape(entry.result or _('N/A'))}</td>
                    <td>{_escape(entry.description or _('N/A'))}</td>
                </tr>
            """

        html_content += """
            </tbody>
        </table>
        """

    html_content += HTML_BODY_CLOSE

    return html_content
