"""
Tests for the multi-tenancy engine seam (Phase 0 of the Pro+ relocation).

The invariant: with no engine registered, OSS behaves exactly as before; when
an engine is registered, the seam points defer to it.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.multitenancy import seam
from backend.persistence import partitions


@pytest.fixture(autouse=True)
def _clean_seam():
    """Ensure no engine leaks between tests."""
    seam.unregister_engine()
    yield
    seam.unregister_engine()


def test_no_engine_by_default():
    assert seam.active_engine() is None
    assert seam.is_engine_present() is False


def test_register_and_unregister():
    eng = MagicMock()
    seam.register_engine(eng)
    assert seam.active_engine() is eng
    assert seam.is_engine_present() is True
    seam.unregister_engine()
    assert seam.active_engine() is None


def test_resolve_engine_uses_registered_engine_for_tenant(engine):
    sentinel = MagicMock(name="tenant-engine")
    fake = MagicMock()
    fake.resolve_tenant_engine.return_value = sentinel
    seam.register_engine(fake)
    with patch.object(partitions.config, "is_multitenancy_enabled", return_value=True):
        result = partitions.resolve_engine(
            partition=partitions.PARTITION_TENANT, tenant_id="t-1"
        )
    assert result is sentinel
    fake.resolve_tenant_engine.assert_called_once_with("t-1")


def test_resolve_engine_falls_back_to_builtin_without_engine(engine):
    # No engine registered → the OSS built-in (OpenBAO TenantEngineManager) path
    # is used.  We only assert it *delegates* there (mocked), proving the
    # fallback wiring, not the lease itself.
    with patch.object(
        partitions.config, "is_multitenancy_enabled", return_value=True
    ), patch("backend.persistence.tenant_engine.get_manager") as get_mgr:
        get_mgr.return_value.get_engine.return_value = "builtin-engine"
        result = partitions.resolve_engine(
            partition=partitions.PARTITION_TENANT, tenant_id="t-1"
        )
    assert result == "builtin-engine"
    get_mgr.return_value.get_engine.assert_called_once_with("t-1")
