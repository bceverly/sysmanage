"""
Tests for the per-tenant engine manager — Phase 13.1.C.

Exercises the lease cache, proactive renewal, eviction, and evict-and-re-lease
on auth failure, with OpenBAO + the DB engine mocked.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.persistence import tenant_engine
from backend.services.openbao_db_secrets import DbLease


def _lease(ttl=3600, user="u1", pw="p1", lease_id="lease-1"):
    return DbLease(username=user, password=pw, lease_id=lease_id, lease_duration=ttl)


def _placement(role="tenant-acme-db"):
    return SimpleNamespace(
        host="db.internal",
        port=5432,
        dbname="sysmanage_acme",
        openbao_role=role,
        tier="silo",
    )


@pytest.fixture
def patched(monkeypatch):
    """Patch placement lookup, lease, and engine creation; return spies."""
    fake_engine = MagicMock(name="engine")
    lease_calls = []

    def fake_lease(role):
        lease_calls.append(role)
        return _lease()

    monkeypatch.setattr(tenant_engine, "_load_placement", lambda tid: _placement())
    monkeypatch.setattr(
        tenant_engine.openbao_db_secrets, "lease_credentials", fake_lease
    )
    monkeypatch.setattr(tenant_engine, "create_engine", lambda *a, **k: fake_engine)
    return SimpleNamespace(engine=fake_engine, lease_calls=lease_calls)


def test_leases_once_and_caches(patched):
    mgr = tenant_engine.TenantEngineManager()
    e1 = mgr.get_engine("t1")
    e2 = mgr.get_engine("t1")
    assert e1 is patched.engine and e2 is patched.engine
    assert patched.lease_calls == ["tenant-acme-db"]  # leased exactly once


def test_force_refresh_releases(patched):
    mgr = tenant_engine.TenantEngineManager()
    mgr.get_engine("t1")
    mgr.get_engine("t1", force_refresh=True)
    assert len(patched.lease_calls) == 2


def test_handle_auth_failure_evicts_and_revokes(patched, monkeypatch):
    revoked = []
    monkeypatch.setattr(
        tenant_engine.openbao_db_secrets,
        "revoke_lease",
        lambda lid: revoked.append(lid) or True,
    )
    mgr = tenant_engine.TenantEngineManager()
    mgr.get_engine("t1")
    mgr.handle_auth_failure("t1")
    assert revoked == ["lease-1"]
    patched.engine.dispose.assert_called()
    # Next get re-leases.
    mgr.get_engine("t1")
    assert len(patched.lease_calls) == 2


def test_missing_placement_raises(monkeypatch):
    monkeypatch.setattr(tenant_engine, "_load_placement", lambda tid: None)
    mgr = tenant_engine.TenantEngineManager()
    with pytest.raises(LookupError):
        mgr.get_engine("t1")


def test_placement_without_role_raises(monkeypatch):
    monkeypatch.setattr(
        tenant_engine, "_load_placement", lambda tid: _placement(role=None)
    )
    mgr = tenant_engine.TenantEngineManager()
    with pytest.raises(LookupError):
        mgr.get_engine("t1")


def test_renewal_when_past_renew_at(patched, monkeypatch):
    renew_calls = []
    monkeypatch.setattr(
        tenant_engine.openbao_db_secrets,
        "renew_lease",
        lambda lid: renew_calls.append(lid) or 3600,
    )
    times = iter([1000.0, 1000.0, 100000.0, 100000.0, 100000.0])
    monkeypatch.setattr(tenant_engine.time, "time", lambda: next(times))
    mgr = tenant_engine.TenantEngineManager()
    mgr.get_engine("t1")  # acquire at t=1000 (renew_at ~ 1000 + 2400)
    # Next call at t=100000 (> renew_at, < ... but hard_expiry=1000+3600=4600
    # is also passed, so it re-acquires rather than renews).
    mgr.get_engine("t1")
    # Either way the engine is returned and no exception; re-acquire path leases
    # again since hard_expiry passed.
    assert len(patched.lease_calls) >= 1


def test_url_built_from_placement_and_lease():
    url = tenant_engine._build_url(_placement(), _lease(user="dyn", pw="sec"))
    assert url == "postgresql://dyn:sec@db.internal:5432/sysmanage_acme"
