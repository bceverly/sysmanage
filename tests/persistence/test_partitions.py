# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the partition resolver — Phase 13.1.A.

In the default (collapsed/homelab) deployment, multi-tenancy is disabled
and every partition must resolve to the single application engine — the
property that makes "stuff it all in one database" work with zero config.
"""

import pytest

from backend.persistence import partitions
from backend.persistence.db import get_engine


def test_collapsed_mode_resolves_every_partition_to_single_engine(engine, monkeypatch):
    """With multitenancy off, all partitions map to the one (test) engine.

    Patch the toggle explicitly so the assertion holds regardless of the
    developer's local ``sysmanage.yaml`` (which may enable multi-tenancy).
    """
    monkeypatch.setattr(partitions.config, "is_multitenancy_enabled", lambda: False)
    single = get_engine()
    for partition in partitions.PARTITIONS:
        assert partitions.resolve_engine(partition=partition) is single


def test_unknown_partition_rejected(engine):
    with pytest.raises(ValueError):
        partitions.resolve_engine(partition="bogus")


# ---------------------------------------------------------------------------
# tenant_engine_for_host — the queue/processor resolver (Phase 13.1 #2).
# Returns None ("use the default application session") unless MT is enabled AND
# the host is bound, so the per-tenant-queue change is inert until binding.
# ---------------------------------------------------------------------------


def test_tenant_engine_for_host_none_when_multitenancy_disabled(engine, monkeypatch):
    monkeypatch.setattr(partitions.config, "is_multitenancy_enabled", lambda: False)
    assert partitions.tenant_engine_for_host("host-1") is None


def test_tenant_engine_for_host_none_for_null_host(engine, monkeypatch):
    # host_id=None (host determined during processing) → no routing.
    monkeypatch.setattr(partitions.config, "is_multitenancy_enabled", lambda: True)
    assert partitions.tenant_engine_for_host(None) is None


def test_tenant_engine_for_host_none_when_host_unbound(engine, monkeypatch):
    monkeypatch.setattr(partitions.config, "is_multitenancy_enabled", lambda: True)
    from backend.services import host_tenant_index

    monkeypatch.setattr(host_tenant_index, "tenant_for_host", lambda hid: None)
    assert partitions.tenant_engine_for_host("host-1") is None


def test_tenant_engine_for_host_resolves_bound_host(engine, monkeypatch):
    monkeypatch.setattr(partitions.config, "is_multitenancy_enabled", lambda: True)
    from backend.services import host_tenant_index

    monkeypatch.setattr(host_tenant_index, "tenant_for_host", lambda hid: "tenant-7")
    sentinel = object()
    captured = {}

    def fake_resolve(partition, tenant_id=None):
        captured["partition"] = partition
        captured["tenant_id"] = tenant_id
        return sentinel

    monkeypatch.setattr(partitions, "resolve_engine", fake_resolve)
    result = partitions.tenant_engine_for_host("host-1")
    assert result is sentinel
    assert captured == {
        "partition": partitions.PARTITION_TENANT,
        "tenant_id": "tenant-7",
    }


def test_registry_session_factory_yields_session(engine):
    """get_registry_db yields a usable session bound to the single engine."""
    gen = partitions.get_registry_db()
    session = next(gen)
    try:
        assert session.get_bind() is get_engine()
    finally:
        gen.close()


def test_tenant_routing_when_enabled(engine, monkeypatch):
    """When multitenancy is enabled, per-tenant routing REQUIRES the licensed
    engine (Phase 2 moat).

    Registry/shared still collapse onto the bootstrap engine.  The per-tenant
    routing logic (engine cache + OpenBAO leasing) now lives only in the
    compiled ``multitenancy_engine``, so with no engine registered the tenant
    path raises a clear RuntimeError rather than silently misrouting.  A missing
    tenant_id is still a clear ValueError, checked before the engine.
    """
    from backend.multitenancy import seam  # noqa: PLC0415

    seam.unregister_engine()  # ensure no engine leaked in from another test
    monkeypatch.setattr(
        "backend.persistence.partitions.config.is_multitenancy_enabled",
        lambda: True,
    )
    # Registry/shared still resolve (to the bootstrap engine).
    assert (
        partitions.resolve_engine(partition=partitions.PARTITION_REGISTRY) is not None
    )
    # Tenant routing without the licensed engine fails loudly — the moat.
    with pytest.raises(RuntimeError, match="licensed multi-tenancy engine"):
        partitions.resolve_engine(
            partition=partitions.PARTITION_TENANT, tenant_id="some-id"
        )
    # And a missing tenant_id is a clear error, checked before the engine.
    with pytest.raises(ValueError):
        partitions.resolve_engine(partition=partitions.PARTITION_TENANT)
