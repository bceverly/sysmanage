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
def ERROR_USER_NOT_FOUND():
    """User not found error message."""
    return _("User not found")


def ERROR_PERMISSION_DENIED():
    """Generic permission denied error message."""
    return _("Permission denied")


# Host-related errors
def ERROR_HOST_NOT_FOUND():
    """Host not found error message."""
    return _("Host not found")


def ERROR_HOST_NOT_REGISTERED():
    """Host not registered error message."""
    return _("Host not registered")


def ERROR_HOST_NOT_ACTIVE():
    """Host is not active error message."""
    return _("Host is not active")


def ERROR_INVALID_HOST_ID():
    """Invalid host ID format error message."""
    return _("Invalid host ID format")


# Distribution-related errors
def ERROR_DISTRIBUTION_NOT_FOUND():
    """Distribution not found error message."""
    return _("Distribution not found")


# Firewall-related errors
def ERROR_INVALID_FIREWALL_ROLE_ID():
    """Invalid firewall role ID format error message."""
    return _("Invalid firewall role ID format")


def ERROR_FIREWALL_ROLE_NOT_FOUND():
    """Firewall role not found error message."""
    return _("Firewall role not found")


def ERROR_VIEW_FIREWALL_ROLES_REQUIRED():
    """Permission denied for firewall roles viewing."""
    return _("Permission denied: VIEW_FIREWALL_ROLES role required")


# Diagnostic-related errors
def ERROR_INVALID_DIAGNOSTIC_ID():
    """Invalid diagnostic ID format error message."""
    return _("Invalid diagnostic ID format")


def ERROR_DIAGNOSTIC_NOT_FOUND():
    """Diagnostic report not found error message."""
    return _("Diagnostic report not found")


# Virtualization-related errors
def ERROR_UNKNOWN():
    """Unknown error message."""
    return _("Unknown error")


def ERROR_WSL_PENDING():
    """WSL feature enablement pending error message."""
    return _("WSL feature enablement pending")


def ERROR_KVM_LINUX_ONLY():
    """KVM Linux-only error message."""
    return _("KVM is only supported on Linux hosts")


# Integration-related constants (for descriptions)
GRAFANA_API_KEY = "Grafana API Key"
GRAFANA_API_KEY_LABEL = "API Key"
MONITORING_SERVER = "Monitoring Server"
GRAYLOG_API_TOKEN = "Graylog API Token"  # nosec B105 - UI label, not a password
GRAYLOG_API_TOKEN_LABEL = "API Token"  # nosec B105 - UI label, not a password
LOG_AGGREGATION_SERVER = "Log Aggregation Server"

# Config management descriptions
CONFIG_SPECIFIC_HOSTNAME_DESC = "Specific hostname to target"
CONFIG_PUSH_ALL_DESC = "Push to all connected agents"

# Timezone suffix
TIMEZONE_UTC_SUFFIX = "+00:00"


# Host status errors
def ERROR_HOST_NOT_FOUND_OR_NOT_ACTIVE():
    """Host not found or not active error message."""
    return _("Host not found or not active")


def ERROR_AGENT_PRIVILEGED_REQUIRED():
    """Repository management requires privileged agent mode."""
    return _("Repository management requires privileged agent mode")


# Current user errors
def ERROR_CURRENT_USER_NOT_FOUND():
    """Current user not found error message."""
    return _("Current user not found")


# Tag-related errors
def ERROR_TAG_NOT_FOUND():
    """Tag not found error message."""
    return _("Tag not found")


def ERROR_TAG_ALREADY_EXISTS():
    """Tag already exists error message."""
    return _("Tag with this name already exists")


def ERROR_EDIT_TAGS_REQUIRED():
    """Permission denied for editing tags."""
    return _("Permission denied: EDIT_TAGS role required")


# Script-related errors
def ERROR_SCRIPT_NOT_FOUND():
    """Script not found error message."""
    return _("Script not found")


AD_HOC_SCRIPT = "ad-hoc script"


def ERROR_UNSUPPORTED_SHELL_TYPE():
    """Unsupported shell type error message."""
    return _("Unsupported shell type: {}")


# Secrets-related errors
def ERROR_SECRET_NOT_FOUND():
    """Secret not found error message."""
    return _("Secret not found")


def ERROR_INVALID_SECRET_ID():
    """Invalid secret ID error message."""
    return _("Invalid secret ID")


SECRETS_NOT_FOUND_KEY = "secrets.not_found"
SECRETS_INVALID_ID_KEY = "secrets.invalid_id"


# OpenBAO-related errors and constants
def ERROR_OPENBAO_NOT_RUNNING():
    """OpenBAO is not running error message."""
    return _("OpenBAO is not running")


OPENBAO_NOT_RUNNING_KEY = "openbao.not_running"
OPENBAO_GENERIC_ERROR_KEY = "openbao.generic_error"
OPENBAO_DEFAULT_URL = "http://127.0.0.1:8200"
SCHTASKS_PATH = "C:\\Windows\\System32\\schtasks.exe"


# Server errors
def ERROR_INTERNAL_SERVER():
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
