"""
Dynamic module loader for Pro+ Cython modules.

Handles downloading, verification, caching, and dynamic loading
of Pro+ Cython extension modules.
"""

import hashlib
import importlib.util
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import aiohttp
from sqlalchemy.orm import sessionmaker

from backend.config.config import get_config
from backend.licensing.features import ModuleCode
from backend.licensing.plugin_bundle_loader import PluginBundleLoader
from backend.persistence import db as db_module
from backend.persistence.models import ProPlusModuleCache
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.module_loader")

# Default modules path
DEFAULT_MODULES_PATH = "/var/lib/sysmanage/modules"

# Module download timeout in seconds
DOWNLOAD_TIMEOUT = 300

# Version check timeout in seconds
VERSION_CHECK_TIMEOUT = 30


class ModuleLoader:
    """
    Loader for Pro+ Cython modules.

    Handles downloading modules from the license server,
    verifying their integrity, and dynamically loading them.
    """

    def __init__(self):
        self._loaded_modules: Dict[str, Any] = {}
        self._initialized = False
        self._plugin_loader = PluginBundleLoader()

    @property
    def loaded_modules(self) -> Dict[str, Any]:
        """Get dictionary of loaded module names to module objects."""
        return self._loaded_modules.copy()

    def _get_modules_path(self) -> str:
        """Get the path for storing downloaded modules."""
        config = get_config()
        license_config = config.get("license", {})
        return license_config.get("modules_path", DEFAULT_MODULES_PATH)

    def _get_download_url(self) -> Optional[str]:
        """Get the base URL for module downloads."""
        config = get_config()
        license_config = config.get("license", {})
        phone_home_url = license_config.get("phone_home_url")
        if phone_home_url:
            return f"{phone_home_url.rstrip('/')}/api/v1/modules/download"
        return None

    def _get_versions_url(self) -> Optional[str]:
        """Get the URL for querying module versions."""
        config = get_config()
        license_config = config.get("license", {})
        phone_home_url = license_config.get("phone_home_url")
        if phone_home_url:
            return f"{phone_home_url.rstrip('/')}/api/v1/modules/versions"
        return None

    def _get_platform_info(self) -> Dict[str, str]:
        """Get current platform information."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Normalize architecture names
        arch_map = {
            "x86_64": "x86_64",
            "amd64": "x86_64",
            "aarch64": "aarch64",
            "arm64": "aarch64",
        }
        architecture = arch_map.get(machine, machine)

        # Get Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

        return {
            "platform": system,
            "architecture": architecture,
            "python_version": python_version,
        }

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-512 hash of a file."""
        sha512 = hashlib.sha512()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha512.update(chunk)
        return sha512.hexdigest()

    def initialize(self) -> None:
        """Initialize the module loader and ensure modules directory exists."""
        if self._initialized:
            return

        modules_path = self._get_modules_path()
        try:
            Path(modules_path).mkdir(parents=True, exist_ok=True)
            logger.info("Modules directory: %s", modules_path)
        except Exception as e:
            logger.error("Failed to create modules directory: %s", e)

        self._plugin_loader.initialize()
        self._initialized = True

    async def ensure_module_available(
        self, module_code: str, version: Optional[str] = None
    ) -> bool:
        """
        Ensure a module is downloaded and available for loading.
        Also ensures the corresponding plugin bundle is downloaded.

        Args:
            module_code: The module code (e.g., "health_engine")
            version: Optional specific version (uses "latest" if not specified)

        Returns:
            True if module is available, False otherwise
        """
        if not self._initialized:
            self.initialize()

        module_ok = True

        # For plugin-only modules (proplus_core), skip Cython loading
        if module_code == "proplus_core":
            await self.ensure_plugin_available(module_code)
            return True

        # Check if already loaded
        if module_code not in self._loaded_modules:
            # Check cache first
            cached_path = self._get_cached_module_path(module_code, version)
            if cached_path and os.path.exists(cached_path):
                module_ok = self._load_module_from_path(module_code, cached_path)
            else:
                # Download if not cached
                module_ok = await self._download_and_cache_module(module_code, version)

        # Also ensure the plugin bundle is available
        await self.ensure_plugin_available(module_code)

        return module_ok

    def _get_cached_module_path(
        self, module_code: str, version: Optional[str] = None
    ) -> Optional[str]:
        """Get the cached module path from database if available."""
        platform_info = self._get_platform_info()

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                query = session.query(ProPlusModuleCache).filter(
                    ProPlusModuleCache.module_code == module_code,
                    ProPlusModuleCache.platform == platform_info["platform"],
                    ProPlusModuleCache.architecture == platform_info["architecture"],
                    ProPlusModuleCache.python_version
                    == platform_info["python_version"],
                )
                if version:
                    query = query.filter(ProPlusModuleCache.version == version)
                else:
                    # Get latest version
                    query = query.order_by(ProPlusModuleCache.downloaded_at.desc())

                cache_entry = query.first()
                if cache_entry:
                    return cache_entry.file_path
                return None
            except Exception as e:
                logger.error("Error querying module cache: %s", e)
                return None

    async def _download_and_cache_module(
        self, module_code: str, version: Optional[str] = None
    ) -> bool:
        """Download a module from the license server and cache it."""
        download_url = self._get_download_url()
        if not download_url:
            logger.warning("No module download URL configured")
            return False

        # Get license key for authentication
        config = get_config()
        license_config = config.get("license", {})
        license_key = license_config.get("key")
        if not license_key:
            logger.warning("No license key configured - cannot download modules")
            return False

        platform_info = self._get_platform_info()
        version_str = version or "latest"

        # Build download URL (license key sent via header)
        url = (
            f"{download_url}/{module_code}/{version_str}/"
            f"{platform_info['platform']}/{platform_info['architecture']}/"
            f"{platform_info['python_version']}"
        )

        modules_path = self._get_modules_path()
        temp_path = os.path.join(modules_path, f"{module_code}.tmp")
        final_path = os.path.join(
            modules_path,
            f"{module_code}_{platform_info['python_version']}.so",
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"X-License-Key": license_key},
                    timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
                ) as response:
                    if response.status != 200:
                        logger.error(
                            "Module download failed: %s returned %d",
                            url,
                            response.status,
                        )
                        return False

                    # Get expected hash from header
                    expected_hash = response.headers.get("X-Content-SHA512")
                    actual_version = response.headers.get(
                        "X-Module-Version", version_str
                    )

                    # Download to temp file
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)

            # Verify hash if provided
            if expected_hash:
                actual_hash = self._compute_file_hash(temp_path)
                if actual_hash.lower() != expected_hash.lower():
                    logger.error(
                        "Module hash mismatch: expected %s, got %s",
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
            self._save_module_to_cache(
                module_code=module_code,
                version=actual_version,
                platform_info=platform_info,
                file_path=final_path,
                file_hash=actual_hash,
            )

            logger.info(
                "Module downloaded: %s v%s for %s/%s Python %s",
                module_code,
                actual_version,
                platform_info["platform"],
                platform_info["architecture"],
                platform_info["python_version"],
            )

            # Load the module
            return self._load_module_from_path(module_code, final_path)

        except aiohttp.ClientError as e:
            logger.error("Module download network error: %s", e)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
        except Exception as e:
            logger.error("Module download error: %s", e)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    def _save_module_to_cache(
        self,
        module_code: str,
        version: str,
        platform_info: Dict[str, str],
        file_path: str,
        file_hash: str,
    ) -> None:
        """Save module information to cache database."""
        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                # Check for existing entry
                existing = (
                    session.query(ProPlusModuleCache)
                    .filter(
                        ProPlusModuleCache.module_code == module_code,
                        ProPlusModuleCache.version == version,
                        ProPlusModuleCache.platform == platform_info["platform"],
                        ProPlusModuleCache.architecture
                        == platform_info["architecture"],
                        ProPlusModuleCache.python_version
                        == platform_info["python_version"],
                    )
                    .first()
                )

                now = datetime.now(timezone.utc).replace(tzinfo=None)

                if existing:
                    existing.file_path = file_path
                    existing.file_hash = file_hash
                    existing.downloaded_at = now
                else:
                    cache_entry = ProPlusModuleCache(
                        module_code=module_code,
                        version=version,
                        platform=platform_info["platform"],
                        architecture=platform_info["architecture"],
                        python_version=platform_info["python_version"],
                        file_path=file_path,
                        file_hash=file_hash,
                        downloaded_at=now,
                    )
                    session.add(cache_entry)

                session.commit()
            except Exception as e:
                logger.error("Failed to save module to cache: %s", e)
                session.rollback()

    def _load_module_from_path(self, module_code: str, file_path: str) -> bool:
        """Dynamically load a module from a file path."""
        try:
            # Create module spec
            spec = importlib.util.spec_from_file_location(module_code, file_path)
            if spec is None or spec.loader is None:
                logger.error("Failed to create module spec for %s", file_path)
                return False

            # Load the module
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_code] = module
            spec.loader.exec_module(module)

            # Store in loaded modules
            self._loaded_modules[module_code] = module

            logger.info("Module loaded: %s from %s", module_code, file_path)
            return True

        except Exception as e:
            logger.error("Failed to load module %s: %s", module_code, e)
            return False

    def is_module_loaded(self, module_code: str) -> bool:
        """Check if a module is currently loaded."""
        return module_code in self._loaded_modules

    def get_module(self, module_code: str) -> Optional[Any]:
        """
        Get a loaded module by its code.

        Args:
            module_code: The module code

        Returns:
            The loaded module object, or None if not loaded
        """
        return self._loaded_modules.get(module_code)

    def unload_module(self, module_code: str) -> bool:
        """
        Unload a module.

        Args:
            module_code: The module code

        Returns:
            True if module was unloaded, False if not loaded
        """
        if module_code in self._loaded_modules:
            del self._loaded_modules[module_code]
            if module_code in sys.modules:
                del sys.modules[module_code]
            logger.info("Module unloaded: %s", module_code)
            return True
        return False

    def get_loaded_module_info(self) -> Dict[str, dict]:
        """Get information about all loaded modules."""
        result = {}
        for code, module in self._loaded_modules.items():
            result[code] = {
                "loaded": True,
                "version": getattr(module, "__version__", "unknown"),
                "file": getattr(module, "__file__", "unknown"),
            }
        return result

    def _get_cached_module_version(self, module_code: str) -> Optional[str]:
        """Get the cached version of a module from the database."""
        platform_info = self._get_platform_info()

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entry = (
                    session.query(ProPlusModuleCache)
                    .filter(
                        ProPlusModuleCache.module_code == module_code,
                        ProPlusModuleCache.platform == platform_info["platform"],
                        ProPlusModuleCache.architecture
                        == platform_info["architecture"],
                        ProPlusModuleCache.python_version
                        == platform_info["python_version"],
                    )
                    .order_by(ProPlusModuleCache.downloaded_at.desc())
                    .first()
                )
                if cache_entry:
                    return cache_entry.version
                return None
            except Exception as e:
                logger.error("Error querying cached module version: %s", e)
                return None

    def _get_cached_module_hash(self, module_code: str) -> Optional[str]:
        """Get the cached file hash of a module from the database."""
        platform_info = self._get_platform_info()

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entry = (
                    session.query(ProPlusModuleCache)
                    .filter(
                        ProPlusModuleCache.module_code == module_code,
                        ProPlusModuleCache.platform == platform_info["platform"],
                        ProPlusModuleCache.architecture
                        == platform_info["architecture"],
                        ProPlusModuleCache.python_version
                        == platform_info["python_version"],
                    )
                    .order_by(ProPlusModuleCache.downloaded_at.desc())
                    .first()
                )
                if cache_entry:
                    return cache_entry.file_hash
                return None
            except Exception as e:
                logger.error("Error querying cached module hash: %s", e)
                return None

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
            logger.error("Version check error: %s", e)
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
        else:
            pass  # Will process below

        results = {}
        for module_code in updates_needed:
            # Unload the module if it's currently loaded
            was_loaded = self.unload_module(module_code)

            # Remove the old cached file
            self._remove_cached_module(module_code)

            # Download the new version
            success = await self._download_and_cache_module(module_code)
            results[module_code] = success

            if success:
                logger.info("Module %s updated successfully", module_code)
            else:
                logger.error("Failed to update module %s", module_code)
                # If it was loaded before, try to reload the old version
                if was_loaded:
                    cached_path = self._get_cached_module_path(module_code)
                    if cached_path and os.path.exists(cached_path):
                        self._load_module_from_path(module_code, cached_path)

        # Also update plugin bundles
        server_versions = await self.query_server_versions()
        plugin_results = await self._plugin_loader.update_plugins(server_versions)
        results.update({f"{k}_plugin": v for k, v in plugin_results.items()})

        return results

    def _remove_cached_module(self, module_code: str) -> None:
        """Remove a module from the local cache (file and database record)."""
        platform_info = self._get_platform_info()

        session_local = sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.get_engine()
        )

        with session_local() as session:
            try:
                cache_entries = (
                    session.query(ProPlusModuleCache)
                    .filter(
                        ProPlusModuleCache.module_code == module_code,
                        ProPlusModuleCache.platform == platform_info["platform"],
                        ProPlusModuleCache.architecture
                        == platform_info["architecture"],
                        ProPlusModuleCache.python_version
                        == platform_info["python_version"],
                    )
                    .all()
                )

                for entry in cache_entries:
                    # Remove the file
                    if entry.file_path and os.path.exists(entry.file_path):
                        try:
                            os.remove(entry.file_path)
                            logger.debug("Removed cached file: %s", entry.file_path)
                        except OSError as e:
                            logger.warning(
                                "Failed to remove file %s: %s", entry.file_path, e
                            )

                    # Remove the database record
                    session.delete(entry)

                session.commit()
                logger.debug("Removed cache entries for module %s", module_code)

            except Exception as e:
                logger.error("Failed to remove cached module %s: %s", module_code, e)
                session.rollback()

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
            logger.error("Module update check failed: %s", e)


# Global module loader instance
module_loader = ModuleLoader()
