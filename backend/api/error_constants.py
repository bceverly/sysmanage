"""
Common error message constants for API modules.

This module centralizes error messages that are used across multiple API files
to reduce code duplication and ensure consistency.

Note: These constants use the i18n _() function to support internationalization.
The constants are defined as functions that return the translated string to ensure
the translation is evaluated at runtime with the correct locale context.
"""

from backend.i18n import _


# Authentication and Authorization
def error_user_not_found():
    """User not found error message."""
    return _("User not found")


def error_permission_denied():
    """Generic permission denied error message."""
    return _("Permission denied")


# Host-related errors
def error_host_not_found():
    """Host not found error message."""
    return _("Host not found")


def error_host_not_registered():
    """Host not registered error message."""
    return _("Host not registered")


def error_host_not_active():
    """Host is not active error message."""
    return _("Host is not active")


def error_invalid_host_id():
    """Invalid host ID format error message."""
    return _("Invalid host ID format")


# Distribution-related errors
def error_distribution_not_found():
    """Distribution not found error message."""
    return _("Distribution not found")


# Firewall-related errors
def error_invalid_firewall_role_id():
    """Invalid firewall role ID format error message."""
    return _("Invalid firewall role ID format")


def error_firewall_role_not_found():
    """Firewall role not found error message."""
    return _("Firewall role not found")


def error_view_firewall_roles_required():
    """Permission denied for firewall roles viewing."""
    return _("Permission denied: VIEW_FIREWALL_ROLES role required")


# Diagnostic-related errors
def error_invalid_diagnostic_id():
    """Invalid diagnostic ID format error message."""
    return _("Invalid diagnostic ID format")


def error_diagnostic_not_found():
    """Diagnostic report not found error message."""
    return _("Diagnostic report not found")


# Virtualization-related errors
def error_unknown():
    """Unknown error message."""
    return _("Unknown error")


def error_wsl_pending():
    """WSL feature enablement pending error message."""
    return _("WSL feature enablement pending")


def error_kvm_linux_only():
    """KVM Linux-only error message."""
    return _("KVM is only supported on Linux hosts")


# Integration-related constants (for descriptions)
GRAFANA_API_KEY = "Grafana API Key"
GRAFANA_API_KEY_LABEL = "API Key"
MONITORING_SERVER = "Monitoring Server"
GRAYLOG_API_TOKEN = "Graylog API Token"  # nosec B105  # UI label, not a password
GRAYLOG_API_TOKEN_LABEL = "API Token"  # nosec B105  # UI label, not a password
LOG_AGGREGATION_SERVER = "Log Aggregation Server"

# Config management descriptions
CONFIG_SPECIFIC_HOSTNAME_DESC = "Specific hostname to target"
CONFIG_PUSH_ALL_DESC = "Push to all connected agents"

# Timezone suffix
TIMEZONE_UTC_SUFFIX = "+00:00"


# Host status errors
def error_host_not_found_or_not_active():
    """Host not found or not active error message."""
    return _("Host not found or not active")


def error_agent_privileged_required():
    """Repository management requires privileged agent mode."""
    return _("Repository management requires privileged agent mode")


# Current user errors
def error_current_user_not_found():
    """Current user not found error message."""
    return _("Current user not found")


# Tag-related errors
def error_tag_not_found():
    """Tag not found error message."""
    return _("Tag not found")


def error_tag_already_exists():
    """Tag already exists error message."""
    return _("Tag with this name already exists")


def error_edit_tags_required():
    """Permission denied for editing tags."""
    return _("Permission denied: EDIT_TAGS role required")


# Script-related errors
def error_script_not_found():
    """Script not found error message."""
    return _("Script not found")


AD_HOC_SCRIPT = "ad-hoc script"


def error_unsupported_shell_type():
    """Unsupported shell type error message."""
    return _("Unsupported shell type: {}")


# Secrets-related errors
def error_secret_not_found():
    """Secret not found error message."""
    return _("Secret not found")


def error_invalid_secret_id():
    """Invalid secret ID error message."""
    return _("Invalid secret ID")


SECRETS_NOT_FOUND_KEY = "secrets.not_found"
SECRETS_INVALID_ID_KEY = "secrets.invalid_id"


# OpenBAO-related errors and constants
def error_openbao_not_running():
    """OpenBAO is not running error message."""
    return _("OpenBAO is not running")


OPENBAO_NOT_RUNNING_KEY = "openbao.not_running"
OPENBAO_GENERIC_ERROR_KEY = "openbao.generic_error"
OPENBAO_DEFAULT_URL = "http://127.0.0.1:8200"
SCHTASKS_PATH = "C:\\Windows\\System32\\schtasks.exe"


# Server errors
def error_internal_server():
    """Internal server error message."""
    return _("Internal server error")


# Report column headers
REPORT_IP_ADDRESS = "IP Address"
REPORT_OS_VERSION = "OS Version"
FILTER_BY_OS_NAME = "Filter by OS name"
FILTER_BY_OS_VERSION = "Filter by OS version"


# HTML report constants
HTML_BODY_CLOSE = """
    </body>
    </html>
    """

HTML_TABLE_CLOSE = """
            </tbody>
        </table>
        """
