"""
Tests for the multi-tenancy engine bridge (Phase 1 of the Pro+ relocation).

The bridge wraps a loaded ``multitenancy_engine`` module in a seam adapter and
registers it, so the OSS data-plane resolver defers to the engine.  Two layers:

  * Mock-engine tests (always run) cover the bridge contract: delegation,
    rejection of an incomplete module, and that the seam + resolver pick it up.
  * A real-engine test imports the actual compiled ``.so`` from the sibling
    Pro+ repo and bridges it end-to-end.  It skips when the ``.so`` isn't
    importable (e.g. OSS-only CI, or a Python-version mismatch), so it never
    couples the OSS suite to the Pro+ build.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.multitenancy import bridge, seam
from backend.persistence import partitions


@pytest.fixture(autouse=True)
def _clean_seam():
    """Ensure no engine leaks between tests."""
    seam.unregister_engine()
    yield
    seam.unregister_engine()


def _fake_engine_module(tenant_engine_sentinel):
    """A stand-in for a loaded multitenancy_engine module."""
    mod = MagicMock(name="multitenancy_engine")
    mod.resolve_tenant_engine.return_value = tenant_engine_sentinel
    mod.get_multitenancy_engine_router.return_value = MagicMock(name="router")
    mod.get_module_info.return_value = {
        "code": "multitenancy_engine",
        "version": "0.1.0",
        "provides_routes": True,
    }
    return mod


def test_bridge_none_is_noop():
    """No engine loaded → bridge is a no-op and the seam stays empty."""
    assert bridge.bridge_loaded_engine(None) is False
    assert seam.is_engine_present() is False


def test_bridge_registers_engine_into_seam():
    sentinel = object()
    mod = _fake_engine_module(sentinel)

    assert bridge.bridge_loaded_engine(mod) is True
    assert seam.is_engine_present() is True


def test_bridge_rejects_incomplete_module():
    """A module missing a required hook must NOT be registered — OSS falls back
    to its built-in single-tenant path rather than half-wiring the engine."""
    mod = MagicMock(name="partial_engine")
    mod.resolve_tenant_engine = "not callable"  # missing/invalid hook

    assert bridge.bridge_loaded_engine(mod) is False
    assert seam.is_engine_present() is False


def test_resolver_routes_through_bridged_engine():
    """End-to-end through the seam: once bridged, the data-plane resolver
    returns the engine's per-tenant engine."""
    sentinel = object()
    mod = _fake_engine_module(sentinel)
    bridge.bridge_loaded_engine(mod)

    with patch.object(partitions.config, "is_multitenancy_enabled", return_value=True):
        result = partitions.resolve_engine(
            partition=partitions.PARTITION_TENANT, tenant_id="t-42"
        )

    assert result is sentinel
    mod.resolve_tenant_engine.assert_called_once_with("t-42")


# ---------------------------------------------------------------------------
# Real compiled-engine end-to-end (skips cleanly when the .so isn't present)
# ---------------------------------------------------------------------------


def test_real_compiled_engine_bridges_into_seam():
    from tests._engine_loader import require_engine

    engine_mod = require_engine("multitenancy_engine")

    # The real module declares the contract...
    info = engine_mod.get_module_info()
    assert info["code"] == "multitenancy_engine"
    assert info["provides_routes"] is True

    # ...and bridges cleanly into the seam.
    assert bridge.bridge_loaded_engine(engine_mod) is True
    assert seam.is_engine_present() is True

    # The resolver hook delegates to the engine's OWN per-tenant manager (Phase 2
    # relocated that logic into the compiled engine).  Patch the engine module's
    # ``get_manager`` so we assert the delegation path without a live OpenBAO /
    # tenant DB.
    fake_manager = MagicMock()
    fake_manager.get_engine.return_value = "leased-engine"
    with patch.object(engine_mod, "get_manager", return_value=fake_manager):
        with patch.object(
            partitions.config, "is_multitenancy_enabled", return_value=True
        ):
            result = partitions.resolve_engine(
                partition=partitions.PARTITION_TENANT, tenant_id="t-1"
            )
    assert result == "leased-engine"
    fake_manager.get_engine.assert_called_once_with("t-1")
