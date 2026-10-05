# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.4: engine updates stage, verify, then swap -- never delete first --
and download a bounded number at a time."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.licensing import module_loader_mixin
from backend.licensing.module_loader import ModuleLoader


@pytest.mark.asyncio
async def test_a_failed_download_never_touches_the_working_engine():
    """The old code unloaded and deleted the engine before downloading, so an
    overloaded license server left the customer with no engine."""
    loader = ModuleLoader()
    with patch.object(
        loader, "check_for_updates", new=AsyncMock(return_value=["a"])
    ), patch.object(loader, "unload_module") as unload, patch.object(
        loader, "_remove_cached_module"
    ) as remove, patch.object(
        loader, "_download_and_cache_module", new=AsyncMock(return_value=False)
    ), patch.object(
        loader, "query_server_versions", new=AsyncMock(return_value={})
    ), patch.object(
        loader._plugin_loader, "update_plugins", new=AsyncMock(return_value={})
    ):
        results = await loader.update_modules()
    assert results == {"a": False}
    unload.assert_not_called()
    remove.assert_not_called()


@pytest.mark.asyncio
async def test_downloads_are_bounded():
    loader = ModuleLoader()
    active = peak = 0

    async def download(_code):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    codes = [f"m{i}" for i in range(10)]
    with patch.object(
        loader, "check_for_updates", new=AsyncMock(return_value=codes)
    ), patch.object(loader, "_download_and_cache_module", new=download), patch.object(
        loader, "query_server_versions", new=AsyncMock(return_value={})
    ), patch.object(
        loader._plugin_loader, "update_plugins", new=AsyncMock(return_value={})
    ):
        results = await loader.update_modules()
    assert all(results[c] for c in codes)
    assert peak == module_loader_mixin.MAX_PARALLEL_DOWNLOADS
