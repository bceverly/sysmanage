"""
HTML report generators
"""

from backend.api.reports.html.hosts import (
    generate_hosts_html,
    generate_firewall_status_html,
    generate_antivirus_opensource_html,
    generate_antivirus_commercial_html,
)
from backend.api.reports.html.users import (
    generate_users_html,
    generate_user_rbac_html,
    generate_audit_log_html,
)

__all__ = [
    "generate_hosts_html",
    "generate_firewall_status_html",
    "generate_antivirus_opensource_html",
    "generate_antivirus_commercial_html",
    "generate_users_html",
    "generate_user_rbac_html",
    "generate_audit_log_html",
]
