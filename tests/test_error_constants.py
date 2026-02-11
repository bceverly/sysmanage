"""
Tests for backend/api/error_constants.py module.
Tests all error message functions and constants.
"""

import pytest


class TestAuthenticationErrors:
    """Tests for authentication and authorization errors."""

    def test_error_user_not_found(self):
        """Test error_user_not_found returns a string."""
        from backend.api.error_constants import error_user_not_found

        result = error_user_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_permission_denied(self):
        """Test error_permission_denied returns a string."""
        from backend.api.error_constants import error_permission_denied

        result = error_permission_denied()
        assert isinstance(result, str)
        assert len(result) > 0


class TestHostErrors:
    """Tests for host-related errors."""

    def test_error_host_not_found(self):
        """Test error_host_not_found returns a string."""
        from backend.api.error_constants import error_host_not_found

        result = error_host_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_host_not_registered(self):
        """Test error_host_not_registered returns a string."""
        from backend.api.error_constants import error_host_not_registered

        result = error_host_not_registered()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_host_not_active(self):
        """Test error_host_not_active returns a string."""
        from backend.api.error_constants import error_host_not_active

        result = error_host_not_active()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_invalid_host_id(self):
        """Test error_invalid_host_id returns a string."""
        from backend.api.error_constants import error_invalid_host_id

        result = error_invalid_host_id()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_host_not_found_or_not_active(self):
        """Test error_host_not_found_or_not_active returns a string."""
        from backend.api.error_constants import error_host_not_found_or_not_active

        result = error_host_not_found_or_not_active()
        assert isinstance(result, str)
        assert len(result) > 0


class TestDistributionErrors:
    """Tests for distribution-related errors."""

    def test_error_distribution_not_found(self):
        """Test error_distribution_not_found returns a string."""
        from backend.api.error_constants import error_distribution_not_found

        result = error_distribution_not_found()
        assert isinstance(result, str)
        assert len(result) > 0


class TestFirewallErrors:
    """Tests for firewall-related errors."""

    def test_error_invalid_firewall_role_id(self):
        """Test error_invalid_firewall_role_id returns a string."""
        from backend.api.error_constants import error_invalid_firewall_role_id

        result = error_invalid_firewall_role_id()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_firewall_role_not_found(self):
        """Test error_firewall_role_not_found returns a string."""
        from backend.api.error_constants import error_firewall_role_not_found

        result = error_firewall_role_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_view_firewall_roles_required(self):
        """Test error_view_firewall_roles_required returns a string."""
        from backend.api.error_constants import error_view_firewall_roles_required

        result = error_view_firewall_roles_required()
        assert isinstance(result, str)
        assert len(result) > 0


class TestDiagnosticErrors:
    """Tests for diagnostic-related errors."""

    def test_error_invalid_diagnostic_id(self):
        """Test error_invalid_diagnostic_id returns a string."""
        from backend.api.error_constants import error_invalid_diagnostic_id

        result = error_invalid_diagnostic_id()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_diagnostic_not_found(self):
        """Test error_diagnostic_not_found returns a string."""
        from backend.api.error_constants import error_diagnostic_not_found

        result = error_diagnostic_not_found()
        assert isinstance(result, str)
        assert len(result) > 0


class TestVirtualizationErrors:
    """Tests for virtualization-related errors."""

    def test_error_unknown(self):
        """Test error_unknown returns a string."""
        from backend.api.error_constants import error_unknown

        result = error_unknown()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_wsl_pending(self):
        """Test error_wsl_pending returns a string."""
        from backend.api.error_constants import error_wsl_pending

        result = error_wsl_pending()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_kvm_linux_only(self):
        """Test error_kvm_linux_only returns a string."""
        from backend.api.error_constants import error_kvm_linux_only

        result = error_kvm_linux_only()
        assert isinstance(result, str)
        assert len(result) > 0


class TestRepositoryErrors:
    """Tests for repository-related errors."""

    def test_error_agent_privileged_required(self):
        """Test error_agent_privileged_required returns a string."""
        from backend.api.error_constants import error_agent_privileged_required

        result = error_agent_privileged_required()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCurrentUserErrors:
    """Tests for current user errors."""

    def test_error_current_user_not_found(self):
        """Test error_current_user_not_found returns a string."""
        from backend.api.error_constants import error_current_user_not_found

        result = error_current_user_not_found()
        assert isinstance(result, str)
        assert len(result) > 0


class TestTagErrors:
    """Tests for tag-related errors."""

    def test_error_tag_not_found(self):
        """Test error_tag_not_found returns a string."""
        from backend.api.error_constants import error_tag_not_found

        result = error_tag_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_tag_already_exists(self):
        """Test error_tag_already_exists returns a string."""
        from backend.api.error_constants import error_tag_already_exists

        result = error_tag_already_exists()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_edit_tags_required(self):
        """Test error_edit_tags_required returns a string."""
        from backend.api.error_constants import error_edit_tags_required

        result = error_edit_tags_required()
        assert isinstance(result, str)
        assert len(result) > 0


class TestScriptErrors:
    """Tests for script-related errors."""

    def test_error_script_not_found(self):
        """Test error_script_not_found returns a string."""
        from backend.api.error_constants import error_script_not_found

        result = error_script_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_unsupported_shell_type(self):
        """Test error_unsupported_shell_type returns a string."""
        from backend.api.error_constants import error_unsupported_shell_type

        result = error_unsupported_shell_type()
        assert isinstance(result, str)
        assert len(result) > 0


class TestSecretErrors:
    """Tests for secrets-related errors."""

    def test_error_secret_not_found(self):
        """Test error_secret_not_found returns a string."""
        from backend.api.error_constants import error_secret_not_found

        result = error_secret_not_found()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_invalid_secret_id(self):
        """Test error_invalid_secret_id returns a string."""
        from backend.api.error_constants import error_invalid_secret_id

        result = error_invalid_secret_id()
        assert isinstance(result, str)
        assert len(result) > 0


class TestOpenBAOErrors:
    """Tests for OpenBAO-related errors."""

    def test_error_openbao_not_running(self):
        """Test error_openbao_not_running returns a string."""
        from backend.api.error_constants import error_openbao_not_running

        result = error_openbao_not_running()
        assert isinstance(result, str)
        assert len(result) > 0


class TestServerErrors:
    """Tests for server errors."""

    def test_error_internal_server(self):
        """Test error_internal_server returns a string."""
        from backend.api.error_constants import error_internal_server

        result = error_internal_server()
        assert isinstance(result, str)
        assert len(result) > 0


class TestIntegrationConstants:
    """Tests for integration-related constants."""

    def test_grafana_constants(self):
        """Test Grafana constants exist."""
        from backend.api.error_constants import (
            GRAFANA_API_KEY,
            GRAFANA_API_KEY_LABEL,
            MONITORING_SERVER,
        )

        assert GRAFANA_API_KEY == "Grafana API Key"
        assert GRAFANA_API_KEY_LABEL == "API Key"
        assert MONITORING_SERVER == "Monitoring Server"

    def test_graylog_constants(self):
        """Test Graylog constants exist."""
        from backend.api.error_constants import (
            GRAYLOG_API_TOKEN,
            GRAYLOG_API_TOKEN_LABEL,
            LOG_AGGREGATION_SERVER,
        )

        assert GRAYLOG_API_TOKEN == "Graylog API Token"
        assert GRAYLOG_API_TOKEN_LABEL == "API Token"
        assert LOG_AGGREGATION_SERVER == "Log Aggregation Server"


class TestConfigManagementConstants:
    """Tests for config management constants."""

    def test_config_constants(self):
        """Test config management constants exist."""
        from backend.api.error_constants import (
            CONFIG_SPECIFIC_HOSTNAME_DESC,
            CONFIG_PUSH_ALL_DESC,
        )

        assert CONFIG_SPECIFIC_HOSTNAME_DESC == "Specific hostname to target"
        assert CONFIG_PUSH_ALL_DESC == "Push to all connected agents"


class TestTimezoneConstants:
    """Tests for timezone constants."""

    def test_timezone_utc_suffix(self):
        """Test timezone UTC suffix constant."""
        from backend.api.error_constants import TIMEZONE_UTC_SUFFIX

        assert TIMEZONE_UTC_SUFFIX == "+00:00"


class TestSecretConstants:
    """Tests for secret-related constants."""

    def test_secret_key_constants(self):
        """Test secret key constants exist."""
        from backend.api.error_constants import (
            SECRETS_NOT_FOUND_KEY,
            SECRETS_INVALID_ID_KEY,
        )

        assert SECRETS_NOT_FOUND_KEY == "secrets.not_found"
        assert SECRETS_INVALID_ID_KEY == "secrets.invalid_id"


class TestOpenBAOConstants:
    """Tests for OpenBAO-related constants."""

    def test_openbao_constants(self):
        """Test OpenBAO constants exist."""
        from backend.api.error_constants import (
            OPENBAO_NOT_RUNNING_KEY,
            OPENBAO_GENERIC_ERROR_KEY,
            OPENBAO_DEFAULT_URL,
            SCHTASKS_PATH,
        )

        assert OPENBAO_NOT_RUNNING_KEY == "openbao.not_running"
        assert OPENBAO_GENERIC_ERROR_KEY == "openbao.generic_error"
        assert OPENBAO_DEFAULT_URL == "http://127.0.0.1:8200"
        assert SCHTASKS_PATH == "C:\\Windows\\System32\\schtasks.exe"


class TestReportConstants:
    """Tests for report-related constants."""

    def test_report_constants(self):
        """Test report constants exist."""
        from backend.api.error_constants import (
            REPORT_IP_ADDRESS,
            REPORT_OS_VERSION,
            FILTER_BY_OS_NAME,
            FILTER_BY_OS_VERSION,
        )

        assert REPORT_IP_ADDRESS == "IP Address"
        assert REPORT_OS_VERSION == "OS Version"
        assert FILTER_BY_OS_NAME == "Filter by OS name"
        assert FILTER_BY_OS_VERSION == "Filter by OS version"


class TestHTMLConstants:
    """Tests for HTML constants."""

    def test_html_body_close(self):
        """Test HTML body close constant."""
        from backend.api.error_constants import HTML_BODY_CLOSE

        assert "</body>" in HTML_BODY_CLOSE
        assert "</html>" in HTML_BODY_CLOSE

    def test_html_table_close(self):
        """Test HTML table close constant."""
        from backend.api.error_constants import HTML_TABLE_CLOSE

        assert "</tbody>" in HTML_TABLE_CLOSE
        assert "</table>" in HTML_TABLE_CLOSE


class TestScriptConstants:
    """Tests for script constants."""

    def test_ad_hoc_script(self):
        """Test ad hoc script constant."""
        from backend.api.error_constants import AD_HOC_SCRIPT

        assert AD_HOC_SCRIPT == "ad-hoc script"
