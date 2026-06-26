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
    fake = MagicMock()
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
