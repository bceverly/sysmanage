"""
Tests for tenant-aware email config resolution in backend.config.config
(Phase 13.1).  When a tenant is active, its scoped settings/secrets win;
otherwise resolution falls back to the server scope (single-tenant default).
"""

from unittest.mock import patch

from backend.config import config


def test_db_setting_prefers_active_tenant():
    with patch.object(config, "_active_tenant", return_value="t-1"), patch(
        "backend.config.settings_service.get_tenant_setting", return_value="tenant-mx"
    ) as get_tenant, patch(
        "backend.config.settings_service.get_setting", return_value="server-mx"
    ) as get_server:
        assert config._db_setting("email_host") == "tenant-mx"
    get_tenant.assert_called_once()
    get_server.assert_not_called()


def test_db_setting_falls_to_server_when_tenant_value_unset():
    with patch.object(config, "_active_tenant", return_value="t-1"), patch(
        "backend.config.settings_service.get_tenant_setting", return_value=None
    ), patch("backend.config.settings_service.get_setting", return_value="server-mx"):
        assert config._db_setting("email_host") == "server-mx"


def test_db_setting_server_scope_when_no_active_tenant():
    with patch.object(config, "_active_tenant", return_value=None), patch(
        "backend.config.settings_service.get_tenant_setting"
    ) as get_tenant, patch(
        "backend.config.settings_service.get_setting", return_value="server-mx"
    ):
        assert config._db_setting("email_host") == "server-mx"
    get_tenant.assert_not_called()


def test_smtp_password_prefers_active_tenant():
    with patch.object(config, "_active_tenant", return_value="t-1"), patch(
        "backend.config.secrets_service.get_tenant_secret", return_value="tenant-pw"
    ), patch(
        "backend.config.secrets_service.get_secret", return_value="server-pw"
    ) as get_server:
        assert config._smtp_password() == "tenant-pw"
    get_server.assert_not_called()


def test_smtp_password_falls_to_server_when_tenant_secret_absent():
    with patch.object(config, "_active_tenant", return_value="t-1"), patch(
        "backend.config.secrets_service.get_tenant_secret", return_value=None
    ), patch("backend.config.secrets_service.get_secret", return_value="server-pw"):
        assert config._smtp_password() == "server-pw"


def test_active_tenant_never_raises():
    # Even if the context module blows up, resolution must degrade gracefully.
    with patch(
        "backend.persistence.tenant_context.get_active_tenant",
        side_effect=RuntimeError("boom"),
    ):
        assert config._active_tenant() is None
