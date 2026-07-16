# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the startup secrets overlay (Phase 13.1.H).

Verifies that OpenBAO config secrets are overlaid onto the live config dict
and the auth_handler.JWT_SECRET global, and that it's a safe no-op when the
bag is empty.
"""

from unittest.mock import patch

import backend.auth.auth_handler as auth_handler
from backend.config import config, secrets_bootstrap


def test_overlay_updates_config_and_jwt_secret():
    fake_bag = {
        "jwt_secret": "bao-jwt",
        "password_salt": "bao-salt",
        "admin_password": "bao-admin",
        "db_password": "bao-db",
    }
    cfg = {"security": {}, "database": {}, "registry": {}}
    original_jwt = auth_handler.JWT_SECRET
    try:
        with patch(
            "backend.config.secrets_service.get_config_secret_bag",
            return_value=fake_bag,
        ), patch.object(config, "config", cfg):
            assert secrets_bootstrap.refresh_secrets_from_openbao() is True
        assert cfg["security"]["jwt_secret"] == "bao-jwt"
        assert cfg["security"]["password_salt"] == "bao-salt"
        assert cfg["database"]["password"] == "bao-db"
        assert cfg["registry"]["password"] == "bao-db"
        assert auth_handler.JWT_SECRET == "bao-jwt"
    finally:
        auth_handler.JWT_SECRET = original_jwt


def test_overlay_noop_on_empty_bag():
    original_jwt = auth_handler.JWT_SECRET
    with patch(
        "backend.config.secrets_service.get_config_secret_bag", return_value=None
    ):
        assert secrets_bootstrap.refresh_secrets_from_openbao() is False
    assert auth_handler.JWT_SECRET == original_jwt


def test_overlay_never_raises():
    with patch(
        "backend.config.secrets_service.get_config_secret_bag",
        side_effect=RuntimeError("boom"),
    ):
        assert secrets_bootstrap.refresh_secrets_from_openbao() is False
