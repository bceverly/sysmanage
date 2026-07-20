# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Update / version-query mixin for :class:`ModuleLoader`.

Extracted from ``backend.licensing.module_loader`` to keep that module under the
line-count cap.  ``ModuleLoaderUpdatesMixin`` groups the license-server version
query and the module/plugin update-and-download flow; ``ModuleLoader`` mixes it
in, so every method here remains a ``ModuleLoader`` method with identical
behavior.  The methods depend on attributes/methods defined on ``ModuleLoader``
(e.g. ``self._plugin_loader``, ``self._get_versions_url``); those resolve at
runtime via ``self`` exactly as before.
"""

import asyncio
import os
from typing import Any, Dict, List

import aiohttp

from backend.config.config import get_config
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.module_loader")

# Version check timeout in seconds
VERSION_CHECK_TIMEOUT = 30


class ModuleLoaderUpdatesMixin:
    """License-server version query + module/plugin update flow for ModuleLoader."""

    async def query_server_versions(self) -> Dict[str, Any]:
        """
        Query the license server for latest module and plugin versions.

        Returns:
            Dictionary with "modules" and "plugins" keys, each mapping
            module_code to {"version": str, "file_hash": str}
        """
        versions_url = self._get_versions_url()
        if not versions_url:
            logger.debug("No versions URL configured")
            return {}

        # Get license key for authentication
        config = get_config()
        license_config = config.get("license", {})
        license_key = license_config.get("key")
        if not license_key:
            logger.debug("No license key configured")
            return {}

        platform_info = self._get_platform_info()

        url = (
            f"{versions_url}/"
            f"{platform_info['platform']}/{platform_info['architecture']}/"
            f"{platform_info['python_version']}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"X-License-Key": license_key},
                    timeout=aiohttp.ClientTimeout(total=VERSION_CHECK_TIMEOUT),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Version check failed: %s returned %d",
                            url,
                            response.status,
                        )
                        return {}

                    data = await response.json()

                    # Parse modules
                    modules_result: Dict[str, Dict[str, str]] = {}
                    for mod in data.get("modules", []):
                        modules_result[mod["code"]] = {
                            "version": mod["latest_version"],
                            "file_hash": mod["file_hash"],
                        }

                    # Parse plugins
                    plugins_result: Dict[str, Dict[str, str]] = {}
                    for plugin in data.get("plugins", []):
                        plugins_result[plugin["code"]] = {
                            "version": plugin["latest_version"],
                            "file_hash": plugin["file_hash"],
                        }

                    return {
                        "modules": modules_result,
                        "plugins": plugins_result,
                    }

        except aiohttp.ClientError as e:
            logger.warning("Version check network error: %s", e)
            return {}
        except Exception as e:
            logger.exception("Version check error: %s", e)
            return {}

    async def check_for_updates(self) -> List[str]:
        """
        Check for module updates from the license server.

        Compares both version strings and file hashes so that
        rebuilt modules with the same version number are still
        detected as needing an update.

        Returns:
            List of module codes that have updates available
        """
        server_data = await self.query_server_versions()
        if not server_data:
            return []

        # Handle both old format (flat dict) and new format (nested with modules/plugins)
        server_versions = server_data.get("modules", server_data)
        if not isinstance(server_versions, dict):
            return []

        updates_available = []

        for module_code, server_info in server_versions.items():
            server_version = server_info["version"]
            server_hash = server_info.get("file_hash", "")
            local_version = self._get_cached_module_version(module_code)

            if local_version is None:
                # Module not downloaded yet
                logger.debug("Module %s not yet downloaded", module_code)
                updates_available.append(module_code)
            elif local_version != server_version:
                logger.info(
                    "Module %s has update: %s -> %s",
                    module_code,
                    local_version,
                    server_version,
                )
                updates_available.append(module_code)
            elif server_hash:
                # Same version - compare file hashes to detect rebuilds
                local_hash = self._get_cached_module_hash(module_code)
                if local_hash and local_hash.lower() != server_hash.lower():
                    logger.info(
                        "Module %s v%s has been rebuilt (hash mismatch)",
                        module_code,
                        local_version,
                    )
                    updates_available.append(module_code)
                else:
                    logger.debug(
                        "Module %s is up to date (%s)",
                        module_code,
                        local_version,
                    )
            else:
                logger.debug(
                    "Module %s is up to date (%s)",
                    module_code,
                    local_version,
                )

        return updates_available

    async def update_modules(self) -> Dict[str, bool]:
        """
        Check for and download any module and plugin updates.

        Returns:
            Dictionary mapping module_code to success status
        """
        updates_needed = await self.check_for_updates()
        if not updates_needed:
            logger.info("All modules are up to date")

        # Phase 1: Unload and remove cached modules (fast, synchronous)
        was_loaded_map = {}
        for module_code in updates_needed:
            was_loaded_map[module_code] = self.unload_module(module_code)
            self._remove_cached_module(module_code)

        # Phase 2: Download all modules in parallel
        async def _download_one(mc: str):
            return mc, await self._download_and_cache_module(mc)

        download_results = await asyncio.gather(
            *[_download_one(mc) for mc in updates_needed],
            return_exceptions=True,
        )

        # Phase 3: Process results
        results = {}
        for item in download_results:
            if isinstance(item, Exception):
                logger.error("Module download raised exception: %s", item)
                continue
            module_code, success = item
            results[module_code] = success

            if success:
                logger.info("Module %s updated successfully", module_code)
            else:
                logger.error("Failed to update module %s", module_code)
                cached_path = self._get_cached_module_path(module_code)
                if (
                    was_loaded_map.get(module_code)
                    and cached_path
                    and os.path.exists(cached_path)
                ):
                    self._load_module_from_path(module_code, cached_path)

        # Also update plugin bundles
        server_versions = await self.query_server_versions()
        plugin_results = await self._plugin_loader.update_plugins(server_versions)
        results.update({f"{k}_plugin": v for k, v in plugin_results.items()})

        return results

    # --- Plugin bundle methods (delegated to PluginBundleLoader) ---

    async def ensure_plugin_available(self, module_code: str) -> bool:
        """
        Ensure a plugin bundle is downloaded and available.

        Args:
            module_code: The module code (e.g., "health_engine")

        Returns:
            True if plugin is available, False otherwise
        """
        return await self._plugin_loader.ensure_plugin_available(module_code)

    async def check_for_plugin_updates(self) -> List[str]:
        """
        Check for plugin bundle updates from the license server.

        Returns:
            List of module codes that have plugin updates available
        """
        server_versions = await self.query_server_versions()
        return self._plugin_loader.check_for_plugin_updates(server_versions)

    async def update_plugins(self) -> Dict[str, bool]:
        """
        Check for and download any plugin bundle updates.

        Returns:
            Dictionary mapping module_code to success status
        """
        server_versions = await self.query_server_versions()
        return await self._plugin_loader.update_plugins(server_versions)

    async def check_and_update_on_startup(self) -> None:
        """
        Check for module updates on startup and download if available.

        This should be called during application startup after license validation.
        """
        logger.info("Checking for module updates...")
        try:
            results = await self.update_modules()
            if results:
                updated = [k for k, v in results.items() if v]
                failed = [k for k, v in results.items() if not v]
                if updated:
                    logger.info("Updated modules: %s", ", ".join(updated))
                if failed:
                    logger.warning("Failed to update modules: %s", ", ".join(failed))
            else:
                logger.info("All modules are up to date")
        except Exception as e:
            logger.exception("Module update check failed: %s", e)
