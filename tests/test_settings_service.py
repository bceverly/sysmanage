"""
Tests for the server-scoped settings accessor (Phase 13.1.H).

Verifies DB-first resolution via the server_configuration.settings bag,
YAML fallback with deprecation, set/get round-trip, and the never-raise
behavior when the DB/column isn't available.
"""

import logging

from backend.config import settings_service


def _reset_warned():
    settings_service._warned.clear()
    settings_service.invalidate_cache()


def test_set_then_get_roundtrip(engine):
    _reset_warned()
    assert settings_service.set_setting("jwt_auth_timeout", 1234) is True
    assert settings_service.get_setting("jwt_auth_timeout") == 1234


def test_get_prefers_db_over_yaml(engine):
    _reset_warned()
    settings_service.set_setting("heartbeat_timeout", 9)
    val = settings_service.get_setting("heartbeat_timeout", lambda: 5)
    assert val == 9


def test_get_falls_back_to_yaml_with_deprecation(engine, caplog):
    _reset_warned()
    with caplog.at_level(logging.WARNING):
        val = settings_service.get_setting("cookie_domain", lambda: "example.com")
        # Second read: no DB value, same fallback — warning only once.
        settings_service.get_setting("cookie_domain", lambda: "example.com")
    assert val == "example.com"
    warnings = [r for r in caplog.records if "cookie_domain" in r.message]
    assert len(warnings) == 1


def test_get_returns_default_when_nothing(engine):
    _reset_warned()
    assert settings_service.get_setting("missing", lambda: None, default=42) == 42


def test_multiple_keys_coexist(engine):
    _reset_warned()
    settings_service.set_setting("a", 1)
    settings_service.set_setting("b", "two")
    assert settings_service.get_setting("a") == 1
    assert settings_service.get_setting("b") == "two"


def test_never_raises_without_test_mode():
    # No engine fixture → not in test mode; get_db touches production config.
    # Must degrade to the YAML fallback rather than raising.
    _reset_warned()
    val = settings_service.get_setting("anything", lambda: "fallback", default="d")
    assert val in ("fallback", "d")


# --- Tenant-scoped settings (Phase 13.1) -----------------------------------


def _make_tenant(db_session):
    from backend.persistence.models import RegistryTenant, TENANT_STATUS_ACTIVE

    tenant = RegistryTenant(
        name="Acme", slug="acme-settings", status=TENANT_STATUS_ACTIVE
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


def test_tenant_setting_roundtrip(db_session):
    tenant = _make_tenant(db_session)
    assert (
        settings_service.set_tenant_setting(tenant.id, "email_host", "mx.acme") is True
    )
    assert settings_service.get_tenant_setting(tenant.id, "email_host") == "mx.acme"


def test_tenant_setting_default_when_unset(db_session):
    tenant = _make_tenant(db_session)
    assert (
        settings_service.get_tenant_setting(tenant.id, "email_host", default="d") == "d"
    )


def test_tenant_setting_isolated_from_server(db_session):
    tenant = _make_tenant(db_session)
    settings_service.set_setting("email_host", "server-mx")
    settings_service.set_tenant_setting(tenant.id, "email_host", "tenant-mx")
    # Tenant scope and server scope are independent stores.
    assert settings_service.get_tenant_setting(tenant.id, "email_host") == "tenant-mx"
    assert settings_service.get_setting("email_host") == "server-mx"


def test_set_tenant_setting_unknown_tenant_returns_false(db_session):
    assert settings_service.set_tenant_setting("does-not-exist", "k", "v") is False


def test_get_tenant_setting_never_raises_without_db():
    # No engine fixture → registry unavailable; must degrade to default.
    assert settings_service.get_tenant_setting("any", "email_host", default="d") == "d"
