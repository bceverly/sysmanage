"""
PDF report generator for user-related reports
"""

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from backend.api.reports.pdf.base import ReportGenerator
from backend.i18n import _
from backend.persistence.models import SecurityRole, SecurityRoleGroup, User


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

    def generate_user_rbac_report(self) -> io.BytesIO:
        """Generate User RBAC report showing security roles grouped by role groups"""
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
        content.append(Paragraph(_("User Security Roles (RBAC)"), title_style))
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
            # Get all role groups for organization
            role_groups = (
                self.db.query(SecurityRoleGroup).order_by(SecurityRoleGroup.name).all()
            )

            # Create a user header style
            user_header_style = ParagraphStyle(
                "UserHeader",
                parent=self.styles["Heading2"],
                fontSize=14,
                spaceAfter=10,
                textColor=colors.HexColor("#2196f3"),
            )

            # Create a role group header style
            role_group_style = ParagraphStyle(
                "RoleGroupHeader",
                parent=self.styles["Heading3"],
                fontSize=11,
                spaceBefore=5,
                spaceAfter=5,
                textColor=colors.black,
            )

            # Create a role item style
            role_item_style = ParagraphStyle(
                "RoleItem",
                parent=self.styles["Normal"],
                fontSize=9,
                leftIndent=20,
                spaceAfter=3,
            )

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

                # Add user header
                content.append(Paragraph(user_display_name, user_header_style))

                # Get all roles for this user
                user_roles = list(user.security_roles)

                if not user_roles:
                    content.append(
                        Paragraph(
                            _("No security roles assigned"),
                            role_item_style,
                        )
                    )
                else:
                    # Group roles by their role group
                    for group in role_groups:
                        # Get roles in this group that the user has
                        group_roles = [
                            role for role in user_roles if role.group_id == group.id
                        ]

                        if group_roles:
                            # Add role group header
                            content.append(Paragraph(group.name, role_group_style))

                            # Create multi-column layout for roles using a table
                            sorted_roles = sorted(group_roles, key=lambda r: r.name)

                            # Split roles into 2 columns
                            num_columns = 2
                            roles_per_column = (
                                len(sorted_roles) + num_columns - 1
                            ) // num_columns

                            # Build table data with 2 columns
                            table_data = []
                            for i in range(roles_per_column):
                                row = []
                                for col in range(num_columns):
                                    idx = i + (col * roles_per_column)
                                    if idx < len(sorted_roles):
                                        row.append(f"• {sorted_roles[idx].name}")
                                    else:
                                        row.append("")
                                table_data.append(row)

                            # Create and style the table
                            roles_table = Table(table_data, colWidths=[250, 250])
                            roles_table.setStyle(
                                TableStyle(
                                    [
                                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 20),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ]
                                )
                            )
                            content.append(roles_table)

                # Add spacer between users
                content.append(Spacer(1, 15))

        return self.create_pdf_buffer(_("User Security Roles (RBAC)"), content)

    def generate_audit_log_report(self) -> io.BytesIO:
        """Generate Audit Log report"""
        from backend.persistence.models import AuditLog

        audit_entries = (
            self.db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
        )

        content = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=self.styles["Heading1"],
            fontSize=18,
            spaceAfter=30,
            alignment=1,
        )
        content.append(Paragraph(_("Audit Log"), title_style))
        content.append(Spacer(1, 20))

        # Report metadata
        metadata_style = self.styles["Normal"]
        content.append(
            Paragraph(
                f"{_('Generated')}: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                metadata_style,
            )
        )
        content.append(
            Paragraph(f"{_('Total Entries')}: {len(audit_entries)}", metadata_style)
        )
        content.append(Spacer(1, 20))

        if not audit_entries:
            content.append(
                Paragraph(
                    _("No audit log entries found."),
                    self.styles["Normal"],
                )
            )
        else:
            # Create table data
            table_data = [
                [
                    _("Timestamp"),
                    _("User"),
                    _("Action"),
                    _("Entity Type"),
                    _("Entity Name"),
                    _("Result"),
                    _("Description"),
                ]
            ]

            for entry in audit_entries:
                # Format timestamp
                timestamp_str = (
                    entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if entry.timestamp
                    else _("N/A")
                )

                # Get username or system
                username = entry.username if entry.username else _("System")

                table_data.append(
                    [
                        timestamp_str,
                        username,
                        entry.action_type or _("N/A"),
                        entry.entity_type or _("N/A"),
                        entry.entity_name or _("N/A"),
                        entry.result or _("N/A"),
                        entry.description or _("N/A"),
                    ]
                )

            # Create table with smaller column widths to fit all columns
            table = Table(
                table_data,
                colWidths=[75, 60, 55, 65, 75, 50, 120],
                repeatRows=1,
            )
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

        return self.create_pdf_buffer(_("Audit Log"), content)
