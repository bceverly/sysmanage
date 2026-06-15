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


def test_registry_session_factory_yields_session(engine):
    """get_registry_db yields a usable session bound to the single engine."""
    gen = partitions.get_registry_db()
    session = next(gen)
    try:
        assert session.get_bind() is get_engine()
    finally:
        gen.close()


def test_tenant_routing_when_enabled(engine, monkeypatch):
    """When multitenancy is enabled, per-tenant routing leases via OpenBAO.

    Registry/shared still collapse onto the bootstrap engine.  The tenant path
    (13.1.C) routes through the engine manager; with no placement registered it
    fails loudly (LookupError) rather than silently misrouting, and a missing
    tenant_id is a clear ValueError.
    """
    monkeypatch.setattr(
        "backend.persistence.partitions.config.is_multitenancy_enabled",
        lambda: True,
    )
    # Registry/shared still resolve (to the bootstrap engine).
    assert (
        partitions.resolve_engine(partition=partitions.PARTITION_REGISTRY) is not None
    )
    # Tenant routing now goes through the engine manager; an unregistered
    # tenant (no placement) fails loudly.
    with pytest.raises(LookupError):
        partitions.resolve_engine(
            partition=partitions.PARTITION_TENANT, tenant_id="some-id"
        )
    # And a missing tenant_id is a clear error, not a silent fallback.
    with pytest.raises(ValueError):
        partitions.resolve_engine(partition=partitions.PARTITION_TENANT)
