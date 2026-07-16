# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 13.1.F — cross-tenant data-isolation harness.

The enrollment e2e test (``test_tenant_enrollment_e2e.py``) proves ONE tenant's
data plane composes.  This proves the property that actually matters for a SaaS:
**with two provisioned tenants, no read path ever returns tenant A's data while
tenant B is the one in scope** — through the routing seam every endpoint uses
(``get_request_engine`` → ``resolve_engine``), through a real endpoint helper,
through the active-tenant context, through the host→tenant index, and even when
both tenants hold a row with the *same* fqdn.

Runs in OSS CI: the licensed seam (engine resolution + host↔tenant index) is
monkeypatched onto two real in-memory tenant databases, so no compiled engine is
required.  Each tenant gets its own SQLite engine; the root ``engine`` fixture is
the bootstrap / server-scope database.
"""

# pylint: disable=redefined-outer-name

import asyncio
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import config
from backend.persistence import db as db_module
from backend.persistence import models, partitions
from backend.persistence.db import Base
from backend.persistence import tenant_context
from backend.services import enrollment_service, host_tenant_index

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TOKEN_A = "sme_token_a"  # nosec B105 - test fixture token
TOKEN_B = "sme_token_b"  # nosec B105 - test fixture token


def _fresh_engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def two_tenants(engine, monkeypatch):  # noqa: ARG001 - engine sets bootstrap
    """Two real tenant DBs + the licensed seam wired so tenant_id routes to the
    matching engine.  Returns the per-tenant engines and the host→tenant index."""
    eng_a, eng_b = _fresh_engine(), _fresh_engine()
    by_tenant = {TENANT_A: eng_a, TENANT_B: eng_b}
    bindings: dict[str, str] = {}  # host_id -> tenant_id

    monkeypatch.setattr(config, "is_multitenancy_enabled", lambda: True)

    def fake_resolve(partition=partitions.PARTITION_TENANT, tenant_id=None):
        if partition == partitions.PARTITION_TENANT and tenant_id is not None:
            return by_tenant.get(str(tenant_id), db_module.get_engine())
        return db_module.get_engine()

    monkeypatch.setattr(partitions, "resolve_engine", fake_resolve)
    monkeypatch.setattr(
        host_tenant_index,
        "bind_host_to_tenant",
        lambda host_id, tenant_id: bindings.__setitem__(str(host_id), str(tenant_id))
        or True,
    )
    monkeypatch.setattr(
        host_tenant_index,
        "tenant_for_host",
        lambda host_id: bindings.get(str(host_id)),
    )
    # partitions.tenant_engine_for_host consults the (now in-memory) index too.
    monkeypatch.setattr(
        partitions,
        "tenant_for_host",
        lambda host_id: bindings.get(str(host_id)),
        raising=False,
    )
    monkeypatch.setattr(
        enrollment_service,
        "validate_and_consume",
        lambda session, token: {TOKEN_A: TENANT_A, TOKEN_B: TENANT_B}.get(token),
    )

    try:
        yield {"a": eng_a, "b": eng_b, "by_tenant": by_tenant, "bindings": bindings}
    finally:
        # Dispose both StaticPool engines so their single sqlite connection is
        # closed — otherwise pytest reports a ResourceWarning (unclosed database).
        eng_a.dispose()
        eng_b.dispose()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _seed_host(eng, fqdn, **kw):
    """Insert a Host directly into a tenant DB and return its id."""
    hid = uuid.uuid4()
    with sessionmaker(bind=eng)() as s:
        s.add(
            models.Host(
                id=hid,
                fqdn=fqdn,
                ipv4=kw.get("ipv4", "10.0.0.9"),
                approval_status=kw.get("approval_status", "approved"),
                active=True,
            )
        )
        s.commit()
    return str(hid)


def _fqdns_via_seam(tenant_id):
    """Query Host through the SAME routing seam every endpoint uses."""
    with partitions.request_sessionmaker(tenant_id)() as s:
        return {h.fqdn for h in s.query(models.Host).all()}


def _register(fqdn, token):
    from backend.api.host import HostRegistration, register_host

    return asyncio.run(
        register_host(
            HostRegistration(
                active=True,
                fqdn=fqdn,
                hostname=fqdn.split(".")[0],
                ipv4="10.0.0.1",
                enrollment_token=token,
            )
        )
    )


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #


class TestCrossTenantIsolation:
    def test_register_routes_each_host_to_its_own_tenant(self, two_tenants):
        """A-token host lands in A; B-token host lands in B; neither in the other,
        neither in bootstrap; bindings point the right way."""
        ha = _register("web.a.example.com", TOKEN_A)
        hb = _register("web.b.example.com", TOKEN_B)

        assert _fqdns_via_seam(TENANT_A) == {"web.a.example.com"}
        assert _fqdns_via_seam(TENANT_B) == {"web.b.example.com"}
        # nothing leaked to the bootstrap/server-scope DB
        with sessionmaker(bind=db_module.get_engine())() as s:
            assert s.query(models.Host).count() == 0
        assert two_tenants["bindings"][str(ha.id)] == TENANT_A
        assert two_tenants["bindings"][str(hb.id)] == TENANT_B

    def test_read_seam_never_returns_the_other_tenant(self, two_tenants):
        """The crux: seed distinct hosts in each DB and assert neither tenant's
        query ever sees the other's row."""
        _seed_host(two_tenants["a"], "only-a.example.com")
        _seed_host(two_tenants["b"], "only-b.example.com")

        a, b = _fqdns_via_seam(TENANT_A), _fqdns_via_seam(TENANT_B)
        assert a == {"only-a.example.com"}
        assert b == {"only-b.example.com"}
        assert a.isdisjoint(b)

    def test_real_endpoint_helper_isolates(self, two_tenants):
        """The actual ``_get_all_hosts_sync`` endpoint helper, given a tenant id,
        returns only that tenant's hosts."""
        from backend.api.host import _get_all_hosts_sync

        _seed_host(two_tenants["a"], "host-a.example.com")
        _seed_host(two_tenants["b"], "host-b.example.com")

        got_a = {h["fqdn"] for h in _get_all_hosts_sync(tenant_id=TENANT_A)}
        got_b = {h["fqdn"] for h in _get_all_hosts_sync(tenant_id=TENANT_B)}
        assert got_a == {"host-a.example.com"}
        assert got_b == {"host-b.example.com"}

    def test_same_fqdn_in_both_tenants_does_not_bleed(self, two_tenants):
        """Identical identifiers must not cause a cross-read: each context sees
        its OWN row id for a shared fqdn."""
        id_a = _seed_host(two_tenants["a"], "shared.example.com")
        id_b = _seed_host(two_tenants["b"], "shared.example.com")
        assert id_a != id_b

        with partitions.request_sessionmaker(TENANT_A)() as s:
            rows = s.query(models.Host).filter_by(fqdn="shared.example.com").all()
            assert [str(r.id) for r in rows] == [id_a]
        with partitions.request_sessionmaker(TENANT_B)() as s:
            rows = s.query(models.Host).filter_by(fqdn="shared.example.com").all()
            assert [str(r.id) for r in rows] == [id_b]

    def test_active_tenant_context_switches_engine(self, two_tenants):
        """``get_request_engine()`` with no explicit id follows the active-tenant
        ContextVar — switching tenants switches engines, reset → bootstrap."""
        tok = tenant_context.set_active_tenant(TENANT_A)
        try:
            assert partitions.get_request_engine() is two_tenants["a"]
            tenant_context.set_active_tenant(TENANT_B)
            assert partitions.get_request_engine() is two_tenants["b"]
        finally:
            tenant_context.reset_active_tenant(tok)
        # back to server scope → bootstrap engine
        assert partitions.get_request_engine() is db_module.get_engine()

    def test_host_tenant_index_routes_each_host_to_its_db(self, two_tenants):
        """The websocket/queue routing index sends each host to its OWN tenant
        engine and never cross-resolves."""
        ha = _register("idx-a.example.com", TOKEN_A)
        hb = _register("idx-b.example.com", TOKEN_B)

        assert partitions.tenant_engine_for_host(str(ha.id)) is two_tenants["a"]
        assert partitions.tenant_engine_for_host(str(hb.id)) is two_tenants["b"]
        # an unknown host is server-scoped (None), never another tenant's engine
        assert partitions.tenant_engine_for_host(str(uuid.uuid4())) is None

    def test_multitenancy_off_collapses_to_bootstrap(self, two_tenants, monkeypatch):
        """Regression guard: with MT disabled the seam ignores tenant ids and
        everything resolves to the single bootstrap engine."""
        monkeypatch.setattr(config, "is_multitenancy_enabled", lambda: False)
        assert partitions.get_request_engine(TENANT_A) is db_module.get_engine()
        assert partitions.get_request_engine(TENANT_B) is db_module.get_engine()
