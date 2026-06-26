"""
Tests for the server-scoped configuration settings API (Phase 13.1.H).

Exercises GET (effective values) and PUT (persist to the DB, read back),
using a real signed token so JWTBearer + get_current_user both pass.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import server_settings
from backend.auth.auth_handler import sign_jwt


def _client():
    app = FastAPI()
    app.include_router(server_settings.router)
    return TestClient(app)


def _auth():
    return {"Authorization": f"Bearer {sign_jwt('admin')}"}


def test_get_returns_known_settings(engine):
    resp = _client().get("/api/settings", headers=_auth())
    assert resp.status_code == 200
    keys = {s["key"] for s in resp.json()["settings"]}
    assert {"heartbeat_timeout", "jwt_auth_timeout", "email_enabled"} <= keys


def test_requires_auth(engine):
    resp = _client().get("/api/settings")
    assert resp.status_code in (401, 403)


def test_put_persists_and_reads_back(engine):
    client = _client()
    put = client.put(
        "/api/settings",
        json={"settings": {"heartbeat_timeout": 11, "email_enabled": True}},
        headers=_auth(),
    )
    assert put.status_code == 200
    by_key = {s["key"]: s["value"] for s in put.json()["settings"]}
    assert by_key["heartbeat_timeout"] == 11
    assert by_key["email_enabled"] is True

    # A fresh GET reflects the persisted DB values.
    got = {
        s["key"]: s["value"]
        for s in client.get("/api/settings", headers=_auth()).json()["settings"]
    }
    assert got["heartbeat_timeout"] == 11
    assert got["email_enabled"] is True


def test_unknown_keys_ignored(engine):
    resp = _client().put(
        "/api/settings",
        json={"settings": {"not_a_real_setting": 999}},
        headers=_auth(),
    )
    assert resp.status_code == 200
    keys = {s["key"] for s in resp.json()["settings"]}
    assert "not_a_real_setting" not in keys


def test_int_coercion(engine):
    client = _client()
    client.put(
        "/api/settings",
        json={"settings": {"jwt_auth_timeout": "7200"}},  # string -> int
        headers=_auth(),
    )
    got = {
        s["key"]: s["value"]
        for s in client.get("/api/settings", headers=_auth()).json()["settings"]
    }
    assert got["jwt_auth_timeout"] == 7200


def test_email_password_is_write_only_and_goes_to_openbao(engine):
    """The SMTP password is stored in OpenBAO (not the settings DB) and never
    returned to the client."""
    from unittest.mock import patch

    client = _client()
    with patch(
        "backend.config.secrets_service.store_config_secrets", return_value=True
    ) as store:
        put = client.put(
            "/api/settings",
            json={"settings": {"email_password": "hunter2"}},
            headers=_auth(),
        )
    assert put.status_code == 200
    # Routed to OpenBAO under the smtp_password key, not set_setting.
    store.assert_called_once()
    assert store.call_args[0][0] == {"smtp_password": "hunter2"}
    # The value is never echoed back.
    pw = next(s for s in put.json()["settings"] if s["key"] == "email_password")
    assert pw["value"] == ""
    assert pw["type"] == "secret"


def test_blank_email_password_does_not_overwrite(engine):
    from unittest.mock import patch

    client = _client()
    with patch(
        "backend.config.secrets_service.store_config_secrets", return_value=True
    ) as store:
        client.put(
            "/api/settings",
            json={"settings": {"email_password": ""}},
            headers=_auth(),
        )
    store.assert_not_called()  # blank = keep current


# --- Per-tenant email scoping (Phase 13.1) ---------------------------------


def test_email_setting_routes_to_tenant_scope_when_mt_enabled(engine):
    from unittest.mock import patch

    client = _client()
    with patch.object(
        server_settings.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(server_settings, "get_active_tenant", return_value="t-9"), patch(
        "backend.config.settings_service.set_tenant_setting", return_value=True
    ) as set_tenant, patch(
        "backend.config.settings_service.set_setting", return_value=True
    ) as set_server:
        put = client.put(
            "/api/settings",
            json={"settings": {"email_host": "mx.tenant"}},
            headers=_auth(),
        )
    assert put.status_code == 200
    set_tenant.assert_called_once_with("t-9", "email_host", "mx.tenant")
    # email did NOT go to the server scope
    assert all(c.args[0] != "email_host" for c in set_server.call_args_list)


def test_non_email_setting_stays_server_scoped_under_mt(engine):
    from unittest.mock import patch

    client = _client()
    with patch.object(
        server_settings.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(server_settings, "get_active_tenant", return_value="t-9"), patch(
        "backend.config.settings_service.set_tenant_setting", return_value=True
    ) as set_tenant, patch(
        "backend.config.settings_service.set_setting", return_value=True
    ) as set_server:
        client.put(
            "/api/settings",
            json={"settings": {"heartbeat_timeout": 7}},
            headers=_auth(),
        )
    set_server.assert_any_call("heartbeat_timeout", 7)
    set_tenant.assert_not_called()


def test_email_password_routes_to_tenant_openbao_when_mt_enabled(engine):
    from unittest.mock import patch

    client = _client()
    with patch.object(
        server_settings.config, "is_multitenancy_enabled", return_value=True
    ), patch.object(server_settings, "get_active_tenant", return_value="t-9"), patch(
        "backend.config.secrets_service.store_tenant_secrets", return_value=True
    ) as store_tenant, patch(
        "backend.config.secrets_service.store_config_secrets", return_value=True
    ) as store_server:
        client.put(
            "/api/settings",
            json={"settings": {"email_password": "hunter2"}},
            headers=_auth(),
        )
    store_tenant.assert_called_once_with("t-9", {"smtp_password": "hunter2"})
    store_server.assert_not_called()


def test_email_uses_server_scope_when_mt_disabled(engine):
    from unittest.mock import patch

    client = _client()
    # Even if a tenant id is somehow present, MT-disabled forces server scope.
    with patch.object(
        server_settings.config, "is_multitenancy_enabled", return_value=False
    ), patch.object(server_settings, "get_active_tenant", return_value="t-9"), patch(
        "backend.config.settings_service.set_tenant_setting", return_value=True
    ) as set_tenant, patch(
        "backend.config.settings_service.set_setting", return_value=True
    ) as set_server:
        client.put(
            "/api/settings",
            json={"settings": {"email_host": "mx.server"}},
            headers=_auth(),
        )
    set_server.assert_any_call("email_host", "mx.server")
    set_tenant.assert_not_called()
