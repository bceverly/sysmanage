# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Changed host -> tenant bindings, read from the real engine (Phase 22).

Each server worker caches bindings and asks the engine every few seconds which
ones changed (``rebound_hosts``).  Runs against the compiled
multitenancy_engine; skips when the engine predates ``rebound_hosts``.
"""

import uuid
from datetime import timedelta

import pytest

from backend.services import host_tenant_index


def _tenant(db_session, slug):
    from backend.persistence.models import TENANT_STATUS_ACTIVE, RegistryTenant

    tenant = RegistryTenant(name=slug, slug=slug, status=TENANT_STATUS_ACTIVE)
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def mt_engine(real_engine):
    if not hasattr(real_engine, "rebound_hosts"):
        pytest.skip(
            "multitenancy_engine predates rebound_hosts (Phase 22): "
            "rebuild it with make build-modules"
        )
    return real_engine


def test_first_call_starts_the_watermark(mt_engine, db_session):
    tenant = _tenant(db_session, "rebound-a")
    host = uuid.uuid4()
    assert mt_engine.bind_host_to_tenant(host, tenant.id)
    hosts, watermark = mt_engine.rebound_hosts(None)
    assert hosts == []
    assert watermark is not None


def test_a_rebound_host_is_reported_and_the_watermark_moves(mt_engine, db_session):
    first, second = _tenant(db_session, "rebound-b"), _tenant(db_session, "rebound-c")
    host = uuid.uuid4()
    mt_engine.bind_host_to_tenant(host, first.id)
    _hosts, watermark = mt_engine.rebound_hosts(None)

    mt_engine.bind_host_to_tenant(host, second.id)  # re-enrolled elsewhere
    hosts, newer = mt_engine.rebound_hosts(watermark)
    assert str(host) in hosts
    assert newer >= watermark


def test_old_bindings_are_not_reported(mt_engine, db_session):
    tenant = _tenant(db_session, "rebound-d")
    old = uuid.uuid4()
    mt_engine.bind_host_to_tenant(old, tenant.id)
    _hosts, watermark = mt_engine.rebound_hosts(None)
    later = watermark + timedelta(seconds=mt_engine.REBOUND_OVERLAP_SECONDS + 60)
    hosts, _newer = mt_engine.rebound_hosts(later)
    assert str(old) not in hosts


def test_the_cache_drops_a_host_rebound_by_another_worker(
    mt_engine, db_session, monkeypatch
):
    first, second = _tenant(db_session, "rebound-e"), _tenant(db_session, "rebound-f")
    host = uuid.uuid4()
    mt_engine.bind_host_to_tenant(host, first.id)
    clock = [1000.0]
    monkeypatch.setattr(host_tenant_index.time, "monotonic", lambda: clock[0])
    assert host_tenant_index.tenant_for_host(host) == str(first.id)

    # Another worker re-binds the host: straight to the engine, so this
    # process's cache is not told.
    mt_engine.bind_host_to_tenant(host, second.id)
    assert host_tenant_index.tenant_for_host(host) == str(first.id)  # cached
    clock[0] += host_tenant_index.POLL_SECONDS
    assert host_tenant_index.tenant_for_host(host) == str(second.id)
