"""
Tests for the config secrets accessor (Phase 13.1.H config classification).

Verifies OpenBAO-first resolution, YAML fallback with deprecation, and the
best-effort/never-raise behavior when vault is disabled or unreachable.
"""

from unittest.mock import MagicMock, patch

from backend.config import secrets_service


def _reset_warned():
    secrets_service._warned.clear()
    secrets_service.invalidate_cache()


def test_prefers_openbao_over_yaml():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"jwt_secret": "from-bao"}
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-bao"


def test_falls_back_to_yaml_when_vault_disabled():
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_falls_back_to_yaml_when_secret_absent_in_bao():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.return_value = {"other": "x"}
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_never_raises_when_vault_unreachable():
    _reset_warned()
    with patch.object(
        secrets_service.config, "is_vault_enabled", return_value=True
    ), patch.object(
        secrets_service.config, "get_vault_mount_path", return_value="secret"
    ), patch(
        "backend.services.vault_service.VaultService"
    ) as vs:
        vs.return_value.retrieve_secret.side_effect = RuntimeError("boom")
        val = secrets_service.get_secret("jwt_secret", lambda: "from-yaml")
    assert val == "from-yaml"


def test_returns_default_when_nothing_available():
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        val = secrets_service.get_secret("missing", lambda: None, default="d")
    assert val == "d"


def test_deprecation_warning_logged_once(caplog):
    _reset_warned()
    with patch.object(secrets_service.config, "is_vault_enabled", return_value=False):
        import logging

        with caplog.at_level(logging.WARNING):
            secrets_service.get_secret("jwt_secret", lambda: "y")
            secrets_service.get_secret("jwt_secret", lambda: "y")
    warnings = [r for r in caplog.records if "jwt_secret" in r.message]
    assert len(warnings) == 1
