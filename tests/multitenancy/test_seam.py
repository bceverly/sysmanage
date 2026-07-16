# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

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


def test_resolve_engine_without_engine_raises(engine):
    # Phase 2 moat: the per-tenant resolver logic now lives ONLY in the licensed
    # engine.  With no engine registered there is no OSS fallback — resolving a
    # tenant database is impossible, and the resolver raises a clear error.
    with patch.object(partitions.config, "is_multitenancy_enabled", return_value=True):
        with pytest.raises(RuntimeError, match="licensed multi-tenancy engine"):
            partitions.resolve_engine(
                partition=partitions.PARTITION_TENANT, tenant_id="t-1"
            )
