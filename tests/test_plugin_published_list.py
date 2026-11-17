# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Engines with no UI plugin are not asked for (2026-11-17).

Every worker asked the license server for every engine's plugin bundle at
startup, UI-less engines included, and the server answered the burst with
429 Too Many Requests: about fifty false ERRORs per start.  The version
check lists the published bundles, so the rest are skipped; a 429 that
still happens is a warning, fetched at the next update check.
"""

# pylint: disable=protected-access

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.licensing import plugin_bundle_loader as pbl
from backend.licensing.module_loader import ModuleLoader

PUBLISHED = {"modules": {}, "plugins": {"alerting_engine": {"version": "1.0.38"}}}


def _download(loader, module_code, tmp_path):
    fetch = AsyncMock(return_value=None)
    with patch.object(
        loader, "_get_plugin_download_url", return_value="https://lic"
    ), patch.object(
        pbl, "get_config", return_value={"license": {"key": "k"}}
    ), patch.object(
        loader, "_get_modules_path", return_value=str(tmp_path)
    ), patch.object(
        loader, "_fetch_bundle_to_temp", fetch
    ):
        asyncio.run(loader._download_plugin_bundle(module_code))
    return fetch


def test_until_the_list_is_known_every_engine_is_asked_for(tmp_path):
    loader = pbl.PluginBundleLoader()
    assert loader.publishes_plugin("ui_less_engine_a")
    assert _download(loader, "ui_less_engine_a", tmp_path).await_count == 1


def test_an_engine_missing_from_the_list_is_not_asked_for(tmp_path):
    loader = pbl.PluginBundleLoader()
    loader.note_published_plugins(PUBLISHED)
    assert not loader.publishes_plugin("ui_less_engine_b")
    assert _download(loader, "ui_less_engine_b", tmp_path).await_count == 0
    assert _download(loader, "alerting_engine", tmp_path).await_count == 1


def test_a_failed_version_check_leaves_the_list_unknown():
    loader = pbl.PluginBundleLoader()
    loader.note_published_plugins({})
    loader.note_published_plugins(None)
    loader.note_published_plugins({"modules": {}})  # an answer with no plugin list
    assert loader.publishes_plugin("anything")
    loader.note_published_plugins({"modules": {}, "plugins": {}})
    assert not loader.publishes_plugin("anything")


def test_each_update_check_refreshes_the_list():
    loader = pbl.PluginBundleLoader()
    with patch.object(loader, "_get_cached_plugin_version", return_value="1.0.38"):
        loader.check_for_plugin_updates(PUBLISHED)
    assert loader.publishes_plugin("alerting_engine")
    assert not loader.publishes_plugin("ui_less_engine_c")


def test_a_429_is_a_warning_naming_the_engine():
    response = MagicMock()
    response.status = 429
    response.json = AsyncMock(return_value={"detail": "Too Many Requests"})
    url = "https://lic/api/v1/modules/download-plugin/malware_engine/latest"
    with patch.object(pbl, "logger") as logger:
        asyncio.run(pbl.PluginBundleLoader._log_failed_download(url, response))
    logger.error.assert_not_called()
    assert logger.warning.call_args.args[1] == "malware_engine"


def test_the_server_asks_for_the_list_once_per_process():
    loader = ModuleLoader()
    query = AsyncMock(return_value=PUBLISHED)
    ensure = AsyncMock(return_value=False)
    with patch.object(loader, "query_server_versions", query), patch.object(
        loader._plugin_loader, "ensure_plugin_available", ensure
    ):
        for code in ("alerting_engine", "malware_engine", "image_mode_engine"):
            asyncio.run(loader.ensure_plugin_available(code))
    assert query.await_count == 1 and ensure.await_count == 3
    assert not loader._plugin_loader.publishes_plugin("malware_engine")


def test_a_version_answer_without_plugins_has_no_plugins_key():
    loader = ModuleLoader()
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"modules": []})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=context)
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)
    with patch.object(
        loader, "_get_versions_url", return_value="https://lic/versions"
    ), patch(
        "backend.licensing.module_loader_mixin.get_config",
        return_value={"license": {"key": "k"}},
    ), patch(
        "backend.licensing.module_loader_mixin.aiohttp.ClientSession",
        return_value=session_context,
    ):
        result = asyncio.run(loader.query_server_versions())
    assert result == {"modules": {}}
