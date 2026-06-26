"""
Tests for the active-tenant request context (Phase 13.1).
"""

from backend.persistence import tenant_context


def test_default_is_none():
    # No tenant bound in a fresh context.
    assert tenant_context.get_active_tenant() is None


def test_set_get_reset_roundtrip():
    token = tenant_context.set_active_tenant("tenant-abc")
    try:
        assert tenant_context.get_active_tenant() == "tenant-abc"
    finally:
        tenant_context.reset_active_tenant(token)
    assert tenant_context.get_active_tenant() is None


def test_set_coerces_to_str():
    token = tenant_context.set_active_tenant(12345)
    try:
        assert tenant_context.get_active_tenant() == "12345"
    finally:
        tenant_context.reset_active_tenant(token)


def test_falsy_tenant_becomes_none():
    token = tenant_context.set_active_tenant("")
    try:
        assert tenant_context.get_active_tenant() is None
    finally:
        tenant_context.reset_active_tenant(token)


def test_reset_with_bad_token_is_noop():
    # Reset tolerates a stale/invalid token without raising.
    tenant_context.reset_active_tenant(None)
    assert tenant_context.get_active_tenant() is None


def test_tenant_scope_sets_and_restores():
    assert tenant_context.get_active_tenant() is None
    with tenant_context.tenant_scope("t-1"):
        assert tenant_context.get_active_tenant() == "t-1"
    assert tenant_context.get_active_tenant() is None


def test_tenant_scope_none_preserves_outer():
    # None must NOT clear an already-active tenant (nested compose cleanly).
    with tenant_context.tenant_scope("outer"):
        with tenant_context.tenant_scope(None):
            assert tenant_context.get_active_tenant() == "outer"
        assert tenant_context.get_active_tenant() == "outer"
    assert tenant_context.get_active_tenant() is None


def test_tenant_scope_none_is_noop_when_no_outer():
    with tenant_context.tenant_scope(None):
        assert tenant_context.get_active_tenant() is None


def test_tenant_scope_nested_override_restores():
    with tenant_context.tenant_scope("a"):
        with tenant_context.tenant_scope("b"):
            assert tenant_context.get_active_tenant() == "b"
        assert tenant_context.get_active_tenant() == "a"
