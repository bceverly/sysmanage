# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""ModuleLoader's behaviour around the signature gate.

Split out of ``test_licensing_module_loader_extended.py`` when that file hit
the repo's 1000-line ceiling.  These belong together anyway: they are about
what the LOADER does when verification fails, as opposed to
``test_licensing_module_signature.py``, which tests the verifier itself.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestUnverifiableCacheHandling:
    """An unsigned cached bundle -- what every pre-signing install has -- must
    be discarded and re-fetched, never loaded and never silently kept."""

    @pytest.mark.asyncio
    async def test_unverifiable_cache_is_discarded_and_redownloaded(self, tmp_path):
        """Every install predating module signing has an unsigned bundle in
        this cache.  Without this path the cache row would block a re-download
        and the engine would never come back -- an upgrade that silently
        disables Pro+."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True
        cache_file = tmp_path / "engine.so"
        cache_file.write_bytes(b"x")

        with patch.object(
            loader, "_get_cached_module_path", return_value=str(cache_file)
        ), patch.object(
            loader, "_cached_module_is_authentic", return_value=False
        ), patch.object(
            loader, "_remove_cached_module"
        ) as remove, patch.object(
            loader, "_load_module_from_path"
        ) as load, patch.object(
            loader,
            "_download_and_cache_module",
            new=AsyncMock(return_value=True),
        ) as download, patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=True)
        ):
            ok = await loader.ensure_module_available("health_engine")

        assert ok is True
        remove.assert_called_once_with("health_engine")
        download.assert_awaited_once()
        load.assert_not_called()  # the unverified copy must never be executed
