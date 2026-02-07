"""
Plugin bundle loader for Pro+ plugin JS bundles.

Handles downloading, verification, and caching of Pro+ plugin
bundles (IIFE JavaScript files served to the frontend).
"""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles
import aiohttp
from sqlalchemy.orm import sessionmaker

from backend.config.config import get_config
from backend.persistence import db as db_module
from backend.persistence.models import ProPlusPluginCache
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.plugin_bundle_loader")

# Default modules path
DEFAULT_MODULES_PATH = "/var/lib/sysmanage/modules"

# Plugin download timeout in seconds
DOWNLOAD_TIMEOUT = 300


class PluginBundleLoader:
    """
    Loader for Pro+ plugin JS bundles.

    Handles downloading plugin bundles from the license server,
    verifying their integrity, and caching them locally.
    """

    def __init__(self):
        self._initialized = False

    def _get_modules_path(self) -> str:
        """Get the path for storing downloaded modules."""
        config = get_config()
        license_config = config.get("license", {})
        return license_config.get("modules_path", DEFAULT_MODULES_PATH)

    def _get_plugin_download_url(self) -> Optional[str]:
        """Get the base URL for plugin bundle downloads."""
        config = get_config()
        license_config = config.get("license", {})
        phone_home_url = license_config.get("phone_home_url")
        if phone_home_url:
            return f"{phone_home_url.rstrip('/')}/api/v1/modules/download-plugin"
        return None

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-512 hash of a file."""
        sha512 = hashlib.sha512()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha512.update(chunk)
        return sha512.hexdigest()

    def initialize(self) -> None:
        """Initialize the plugin loader and ensure modules directory exists."""
        if self._initialized:
            return

        modules_path = self._get_modules_path()
        try:
            Path(modules_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create modules directory: %s", e)

        self._initialized = True

    def _get_cached_plugin_version(self, module_code: str) -> Optional[str]:
        """Get the cached version of a plugin bundle from the database."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entry = (
                    session.query(ProPlusPluginCache)
                    .filter(ProPlusPluginCache.module_code == module_code)
                    .order_by(ProPlusPluginCache.downloaded_at.desc())
                    .first()
                )
                if cache_entry:
                    return cache_entry.version
                return None
            except Exception as e:
                logger.error("Error querying cached plugin version: %s", e)
                return None

    def _get_cached_plugin_hash(self, module_code: str) -> Optional[str]:
        """Get the cached file hash of a plugin bundle from the database."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entry = (
                    session.query(ProPlusPluginCache)
                    .filter(ProPlusPluginCache.module_code == module_code)
                    .order_by(ProPlusPluginCache.downloaded_at.desc())
                    .first()
                )
                if cache_entry:
                    return cache_entry.file_hash
                return None
            except Exception as e:
                logger.error("Error querying cached plugin hash: %s", e)
                return None

    async def _download_plugin_bundle(
        self, module_code: str, version: Optional[str] = None
    ) -> bool:
        """Download a plugin JS bundle from the license server."""
        download_url = self._get_plugin_download_url()
        if not download_url:
            logger.warning("No plugin download URL configured")
            return False

        config = get_config()
        license_config = config.get("license", {})
        license_key = license_config.get("key")
        if not license_key:
            logger.warning("No license key configured - cannot download plugins")
            return False

        version_str = version or "latest"
        url = f"{download_url}/{module_code}/{version_str}"

        modules_path = self._get_modules_path()
        temp_path = os.path.join(modules_path, f"{module_code}-plugin.tmp")
        final_path = os.path.join(modules_path, f"{module_code}-plugin.iife.js")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"X-License-Key": license_key},
                    timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "Plugin download failed: %s returned %d",
                            url,
                            response.status,
                        )
                        return False

                    expected_hash = response.headers.get("X-Content-SHA512")
                    actual_version = response.headers.get(
                        "X-Module-Version", version_str
                    )

                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)

            # Verify hash if provided
            if expected_hash:
                actual_hash = self._compute_file_hash(temp_path)
                if actual_hash.lower() != expected_hash.lower():
                    logger.error(
                        "Plugin hash mismatch: expected %s, got %s",
                        expected_hash,
                        actual_hash,
                    )
                    os.remove(temp_path)
                    return False
            else:
                actual_hash = self._compute_file_hash(temp_path)

            # Move to final location
            os.rename(temp_path, final_path)

            # Save to cache database
            self._save_plugin_to_cache(
                module_code=module_code,
                version=actual_version,
                file_path=final_path,
                file_hash=actual_hash,
            )

            logger.info(
                "Plugin bundle downloaded: %s v%s",
                module_code,
                actual_version,
            )
            return True

        except aiohttp.ClientError as e:
            logger.error("Plugin download network error: %s", e)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
        except Exception as e:
            logger.error("Plugin download error: %s", e)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    def _save_plugin_to_cache(
        self,
        module_code: str,
        version: str,
        file_path: str,
        file_hash: str,
    ) -> None:
        """Save plugin bundle information to cache database."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                existing = (
                    session.query(ProPlusPluginCache)
                    .filter(
                        ProPlusPluginCache.module_code == module_code,
                    )
                    .first()
                )

                now = datetime.now(timezone.utc).replace(tzinfo=None)

                if existing:
                    existing.version = version
                    existing.file_path = file_path
                    existing.file_hash = file_hash
                    existing.downloaded_at = now
                else:
                    cache_entry = ProPlusPluginCache(
                        module_code=module_code,
                        version=version,
                        file_path=file_path,
                        file_hash=file_hash,
                        downloaded_at=now,
                    )
                    session.add(cache_entry)

                session.commit()
            except Exception as e:
                logger.error("Failed to save plugin to cache: %s", e)
                session.rollback()

    def _remove_cached_plugin(self, module_code: str) -> None:
        """Remove a plugin from the local cache (file and database record)."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entries = (
                    session.query(ProPlusPluginCache)
                    .filter(ProPlusPluginCache.module_code == module_code)
                    .all()
                )

                for entry in cache_entries:
                    if entry.file_path and os.path.exists(entry.file_path):
                        try:
                            os.remove(entry.file_path)
                            logger.debug("Removed cached plugin: %s", entry.file_path)
                        except OSError as e:
                            logger.warning(
                                "Failed to remove plugin %s: %s", entry.file_path, e
                            )
                    session.delete(entry)

                session.commit()
            except Exception as e:
                logger.error("Failed to remove cached plugin %s: %s", module_code, e)
                session.rollback()

    async def ensure_plugin_available(self, module_code: str) -> bool:
        """
        Ensure a plugin bundle is downloaded and available.

        Args:
            module_code: The module code (e.g., "health_engine")

        Returns:
            True if plugin is available, False otherwise
        """
        if not self._initialized:
            self.initialize()

        modules_path = self._get_modules_path()
        plugin_path = os.path.join(modules_path, f"{module_code}-plugin.iife.js")

        if os.path.exists(plugin_path):
            return True

        return await self._download_plugin_bundle(module_code)

    async def check_for_plugin_updates(self, server_versions: Dict) -> List[str]:
        """
        Check for plugin bundle updates given server version data.

        Args:
            server_versions: The result of query_server_versions(),
                             a dict with "modules" and "plugins" keys.

        Returns:
            List of module codes that have plugin updates available
        """
        if not server_versions:
            return []

        plugin_versions = server_versions.get("plugins", {})
        updates_available = []

        for module_code, server_info in plugin_versions.items():
            server_version = server_info["version"]
            server_hash = server_info.get("file_hash", "")
            local_version = self._get_cached_plugin_version(module_code)

            if local_version is None:
                logger.debug("Plugin %s not yet downloaded", module_code)
                updates_available.append(module_code)
            elif local_version != server_version:
                logger.info(
                    "Plugin %s has update: %s -> %s",
                    module_code,
                    local_version,
                    server_version,
                )
                updates_available.append(module_code)
            elif server_hash:
                local_hash = self._get_cached_plugin_hash(module_code)
                if local_hash and local_hash.lower() != server_hash.lower():
                    logger.info(
                        "Plugin %s v%s has been rebuilt (hash mismatch)",
                        module_code,
                        local_version,
                    )
                    updates_available.append(module_code)

        return updates_available

    async def update_plugins(self, server_versions: Dict) -> Dict[str, bool]:
        """
        Check for and download any plugin bundle updates.

        Args:
            server_versions: The result of query_server_versions(),
                             a dict with "modules" and "plugins" keys.

        Returns:
            Dictionary mapping module_code to success status
        """
        updates_needed = await self.check_for_plugin_updates(server_versions)
        if not updates_needed:
            logger.info("All plugin bundles are up to date")
            return {}

        results = {}
        for module_code in updates_needed:
            self._remove_cached_plugin(module_code)
            success = await self._download_plugin_bundle(module_code)
            results[module_code] = success

            if success:
                logger.info("Plugin %s updated successfully", module_code)
            else:
                logger.error("Failed to update plugin %s", module_code)

        return results
