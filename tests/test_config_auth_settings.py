# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.H — auth-path config getters (JWT timeouts, cookie domain,
recovery-account password).

These accessors moved off direct ``sysmanage.yaml`` reads:

* ``jwt_auth_timeout`` / ``jwt_refresh_timeout`` / ``cookie_domain`` resolve
  **DB-backed Settings first, YAML fallback** (operational config).
* ``admin_password`` (the recovery-account secret) resolves **OpenBAO first,
  YAML fallback** — so the recovery credential need not sit in plaintext YAML.

The tests pin both halves of each accessor: the DB/OpenBAO-first path and the
YAML-fallback path (simulated by having the service delegate to the
``yaml_getter``, exactly as a DB/vault miss does).
"""

from unittest.mock import patch

import backend.config.config as _cfg
from backend.config.config import (
    get_admin_password,
    get_cookie_domain,
    get_jwt_auth_timeout,
    get_jwt_refresh_timeout,
)


def _settings_miss(key, yaml_getter=None, *, default=None):
    """Stand-in for settings_service.get_setting on a DB miss → YAML fallback.

    Mirrors the real contract: return the YAML value when present (not None),
    otherwise ``default``.
    """
    if yaml_getter is not None:
        try:
            legacy = yaml_getter()
        except Exception:  # noqa: BLE001 - missing key → fall through to default
            legacy = None
        if legacy is not None:
            return legacy
    return default


def _secret_miss(name, yaml_getter=None, *, default=None):
    """Stand-in for secrets_service.get_secret on a vault miss → YAML fallback.

    Mirrors the real contract: return the YAML value when truthy, else ``default``.
    """
    if yaml_getter is not None:
        try:
            legacy = yaml_getter()
        except Exception:  # noqa: BLE001
            legacy = None
        if legacy:
            return legacy
    return default


class TestJwtTimeouts:
    def test_auth_timeout_db_first(self):
        with patch.object(_cfg, "_server_setting") as m:
            m.return_value = "7200"  # DB may store as string; getter coerces
            assert get_jwt_auth_timeout() == 7200
            assert m.call_args.args[0] == "jwt_auth_timeout"

    def test_auth_timeout_yaml_fallback(self):
        with patch("backend.config.settings_service.get_setting", _settings_miss):
            with patch.object(_cfg, "config", {"security": {"jwt_auth_timeout": 1234}}):
                assert get_jwt_auth_timeout() == 1234

    def test_auth_timeout_default_when_absent(self):
        with patch("backend.config.settings_service.get_setting", _settings_miss):
            with patch.object(_cfg, "config", {"security": {}}):
                assert get_jwt_auth_timeout() == 3600

    def test_refresh_timeout_db_first(self):
        with patch.object(_cfg, "_server_setting") as m:
            m.return_value = 99999
            assert get_jwt_refresh_timeout() == 99999
            assert m.call_args.args[0] == "jwt_refresh_timeout"

    def test_refresh_timeout_yaml_fallback(self):
        with patch("backend.config.settings_service.get_setting", _settings_miss):
            with patch.object(
                _cfg, "config", {"security": {"jwt_refresh_timeout": 4242}}
            ):
                assert get_jwt_refresh_timeout() == 4242


class TestCookieDomain:
    def test_db_first(self):
        with patch.object(_cfg, "_server_setting", return_value="example.com"):
            assert get_cookie_domain() == "example.com"

    def test_yaml_fallback(self):
        with patch("backend.config.settings_service.get_setting", _settings_miss):
            with patch.object(
                _cfg, "config", {"security": {"cookie_domain": "corp.example"}}
            ):
                assert get_cookie_domain() == "corp.example"

    def test_empty_normalized_to_none(self):
        # An empty string must become None so the Set-Cookie Domain attribute is
        # omitted (RFC 6265 host-scoped default) rather than set to "".
        with patch.object(_cfg, "_server_setting", return_value=""):
            assert get_cookie_domain() is None

    def test_absent_is_none(self):
        with patch("backend.config.settings_service.get_setting", _settings_miss):
            with patch.object(_cfg, "config", {"security": {}}):
                assert get_cookie_domain() is None


class TestAdminPassword:
    def test_openbao_first(self):
        with patch.object(_cfg, "_config_secret") as m:
            m.return_value = "vault-recovery-pw"
            assert get_admin_password() == "vault-recovery-pw"
            assert m.call_args.args[0] == "admin_password"

    def test_yaml_fallback(self):
        with patch("backend.config.secrets_service.get_secret", _secret_miss):
            with patch.object(
                _cfg, "config", {"security": {"admin_password": "yaml-recovery-pw"}}
            ):
                assert get_admin_password() == "yaml-recovery-pw"

    def test_default_empty_when_absent(self):
        with patch("backend.config.secrets_service.get_secret", _secret_miss):
            with patch.object(_cfg, "config", {"security": {}}):
                assert get_admin_password() == ""
