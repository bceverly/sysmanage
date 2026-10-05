# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for the host→tenant index OSS shim (Pro+ relocation, Phase 2).

The implementation moved into the licensed engine; the OSS module is now a thin
delegator.  Here we verify its contract: it routes to the engine module when
present, and degrades to the best-effort no-op (writes False, read None) when
multi-tenancy isn't active.  The real DB logic is covered in the Pro+ engine.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from backend.multitenancy import seam
from backend.services import host_tenant_index


@pytest.fixture(autouse=True)
def _clean_seam():
    seam.unregister_engine()
    yield
    seam.unregister_engine()


def test_no_engine_degrades_gracefully():
    host_id = uuid.uuid4()
    assert host_tenant_index.bind_host_to_tenant(host_id, "t-1") is False
    assert host_tenant_index.tenant_for_host(host_id) is None
    assert host_tenant_index.tenant_for_host(None) is None
    assert host_tenant_index.unbind_host(host_id) is False


def test_delegates_to_engine_when_present():
    fake = MagicMock(rebound_hosts=None)
    fake.bind_host_to_tenant.return_value = True
    fake.tenant_for_host.return_value = "tenant-9"
    fake.unbind_host.return_value = True
    seam.register_engine(MagicMock(), module=fake)

    assert host_tenant_index.bind_host_to_tenant("h-1", "t-1") is True
    fake.bind_host_to_tenant.assert_called_once_with("h-1", "t-1")
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-9"
    fake.tenant_for_host.assert_called_once_with("h-1")
    assert host_tenant_index.unbind_host("h-1") is True
    fake.unbind_host.assert_called_once_with("h-1")


def _engine(tenant="tenant-9", rebound=None):
    """An engine; ``rebound`` is its rebound_hosts (None: an older engine
    that cannot report changed bindings, so the short TTL applies)."""
    fake = MagicMock()
    fake.tenant_for_host.return_value = tenant
    fake.rebound_hosts = rebound
    seam.register_engine(MagicMock(), module=fake)
    return fake


def test_found_binding_is_cached():
    fake = _engine()
    for _ in range(5):
        assert host_tenant_index.tenant_for_host("h-1") == "tenant-9"
    assert fake.tenant_for_host.call_count == 1


def test_miss_is_never_cached():
    """A host being enrolled must not be pinned to the bootstrap database."""
    fake = _engine(tenant=None)
    assert host_tenant_index.tenant_for_host("h-1") is None
    fake.tenant_for_host.return_value = "tenant-2"
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-2"


def test_entry_expires_after_ttl(monkeypatch):
    fake = _engine()
    clock = [1000.0]
    monkeypatch.setattr(host_tenant_index.time, "monotonic", lambda: clock[0])
    host_tenant_index.tenant_for_host("h-1")
    fake.tenant_for_host.return_value = "tenant-3"
    clock[0] += host_tenant_index.CACHE_TTL_SECONDS - 1
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-9"
    clock[0] += 2
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-3"


@pytest.mark.parametrize("change", ["bind", "unbind"])
def test_bind_and_unbind_drop_the_entry(change):
    fake = _engine()
    host_tenant_index.tenant_for_host("h-1")
    fake.tenant_for_host.return_value = "tenant-4" if change == "bind" else None
    if change == "bind":
        host_tenant_index.bind_host_to_tenant("h-1", "tenant-4")
    else:
        host_tenant_index.unbind_host("h-1")
    assert host_tenant_index.tenant_for_host("h-1") == fake.tenant_for_host.return_value


def test_uuid_and_string_share_an_entry():
    fake = _engine()
    host = uuid.uuid4()
    host_tenant_index.tenant_for_host(host)
    host_tenant_index.tenant_for_host(str(host))
    assert fake.tenant_for_host.call_count == 1


def test_cache_is_bounded(monkeypatch):
    _engine()
    monkeypatch.setattr(host_tenant_index, "CACHE_MAX_ENTRIES", 3)
    for i in range(10):
        host_tenant_index.tenant_for_host(f"h-{i}")
    assert len(host_tenant_index._cache) <= 3  # pylint: disable=protected-access


# -- changed bindings reported by the engine (rebound_hosts) ---------------------


class _Rebound:
    """A fake rebound_hosts: hands out queued host lists, records each call."""

    def __init__(self):
        self.pending = []
        self.calls = []
        self.fail = False

    def __call__(self, since):
        self.calls.append(since)
        if self.fail:
            raise RuntimeError("registry down")
        hosts, self.pending = self.pending, []
        return hosts, (since or 0) + 1


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(host_tenant_index.time, "monotonic", lambda: now[0])
    return now


def test_long_ttl_when_the_engine_reports_changes(clock):
    rebound = _Rebound()
    fake = _engine(rebound=rebound)
    host_tenant_index.tenant_for_host("h-1")
    fake.tenant_for_host.return_value = "tenant-3"
    clock[0] += host_tenant_index.CACHE_TTL_SECONDS * 5  # the old TTL, long gone
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-9"
    clock[0] += host_tenant_index.LONG_TTL_SECONDS * 1.2
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-3"


def test_a_binding_changed_by_another_worker_is_dropped(clock):
    rebound = _Rebound()
    fake = _engine(rebound=rebound)
    host_tenant_index.tenant_for_host("h-1")
    host_tenant_index.tenant_for_host("h-2")
    fake.tenant_for_host.return_value = "tenant-5"
    rebound.pending = ["h-1"]  # re-bound by another worker
    clock[0] += host_tenant_index.POLL_SECONDS
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-5"
    assert host_tenant_index.tenant_for_host("h-2") == "tenant-9"  # untouched


def test_polls_at_most_every_poll_seconds_and_passes_the_watermark(clock):
    rebound = _Rebound()
    _engine(rebound=rebound)
    for _ in range(10):
        host_tenant_index.tenant_for_host("h-1")
    assert rebound.calls == [None]
    clock[0] += host_tenant_index.POLL_SECONDS
    host_tenant_index.tenant_for_host("h-1")
    assert rebound.calls == [None, 1]


def test_a_failed_poll_drops_the_whole_cache(clock):
    rebound = _Rebound()
    fake = _engine(rebound=rebound)
    host_tenant_index.tenant_for_host("h-1")
    rebound.fail = True
    fake.tenant_for_host.return_value = "tenant-7"
    clock[0] += host_tenant_index.POLL_SECONDS
    assert host_tenant_index.tenant_for_host("h-1") == "tenant-7"
    # and starts its watermark over once the registry answers again
    rebound.fail = False
    clock[0] += host_tenant_index.POLL_SECONDS
    host_tenant_index.tenant_for_host("h-1")
    assert rebound.calls[-1] is None
