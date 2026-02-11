"""
Tests for backend/licensing/plugin_bundle_loader.py module.
Tests Pro+ plugin bundle loader functionality.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPluginBundleLoaderConstants:
    """Tests for module constants."""

    def test_default_modules_path(self):
        """Test DEFAULT_MODULES_PATH constant."""
        from backend.licensing.plugin_bundle_loader import DEFAULT_MODULES_PATH

        assert DEFAULT_MODULES_PATH == "/var/lib/sysmanage/modules"

    def test_download_timeout(self):
        """Test DOWNLOAD_TIMEOUT constant."""
        from backend.licensing.plugin_bundle_loader import DOWNLOAD_TIMEOUT

        assert DOWNLOAD_TIMEOUT == 300


class TestPluginBundleLoaderInit:
    """Tests for PluginBundleLoader initialization."""

    def test_init_not_initialized(self):
        """Test initialization sets _initialized to False."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        assert loader._initialized is False


class TestPluginBundleLoaderGetModulesPath:
    """Tests for _get_modules_path method."""

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_get_modules_path_default(self, mock_get_config):
        """Test _get_modules_path returns default when not configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_get_config.return_value = {}

        loader = PluginBundleLoader()
        path = loader._get_modules_path()

        assert path == "/var/lib/sysmanage/modules"

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_get_modules_path_configured(self, mock_get_config):
        """Test _get_modules_path returns configured value."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_get_config.return_value = {"license": {"modules_path": "/custom/path"}}

        loader = PluginBundleLoader()
        path = loader._get_modules_path()

        assert path == "/custom/path"


class TestPluginBundleLoaderGetPluginDownloadUrl:
    """Tests for _get_plugin_download_url method."""

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_get_plugin_download_url_not_configured(self, mock_get_config):
        """Test _get_plugin_download_url returns None when not configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_get_config.return_value = {"license": {}}

        loader = PluginBundleLoader()
        url = loader._get_plugin_download_url()

        assert url is None

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_get_plugin_download_url_configured(self, mock_get_config):
        """Test _get_plugin_download_url returns proper URL."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://license.example.com"}
        }

        loader = PluginBundleLoader()
        url = loader._get_plugin_download_url()

        assert url == "https://license.example.com/api/v1/modules/download-plugin"

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_get_plugin_download_url_strips_trailing_slash(self, mock_get_config):
        """Test _get_plugin_download_url strips trailing slash from base URL."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://license.example.com/"}
        }

        loader = PluginBundleLoader()
        url = loader._get_plugin_download_url()

        assert url == "https://license.example.com/api/v1/modules/download-plugin"


class TestPluginBundleLoaderComputeFileHash:
    """Tests for _compute_file_hash method."""

    def test_compute_file_hash(self, tmp_path):
        """Test _compute_file_hash computes correct SHA-512 hash."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")

        loader = PluginBundleLoader()
        hash_result = loader._compute_file_hash(str(test_file))

        # SHA-512 hash is 128 hex characters
        assert len(hash_result) == 128
        # Verify it's a hex string
        int(hash_result, 16)

    def test_compute_file_hash_consistent(self, tmp_path):
        """Test _compute_file_hash returns consistent results."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"consistent content")

        loader = PluginBundleLoader()
        hash1 = loader._compute_file_hash(str(test_file))
        hash2 = loader._compute_file_hash(str(test_file))

        assert hash1 == hash2


class TestPluginBundleLoaderInitialize:
    """Tests for initialize method."""

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_initialize_creates_directory(self, mock_get_config, tmp_path):
        """Test initialize creates modules directory."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        modules_dir = tmp_path / "modules"
        mock_get_config.return_value = {"license": {"modules_path": str(modules_dir)}}

        loader = PluginBundleLoader()
        loader.initialize()

        assert modules_dir.exists()
        assert loader._initialized is True

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_initialize_skips_if_already_initialized(self, mock_get_config):
        """Test initialize skips if already initialized."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        loader._initialized = True

        # Should not raise or do anything
        loader.initialize()

        assert loader._initialized is True

    @patch("backend.licensing.plugin_bundle_loader.get_config")
    def test_initialize_handles_directory_creation_error(self, mock_get_config):
        """Test initialize handles directory creation errors gracefully."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        # Use an invalid path that can't be created
        mock_get_config.return_value = {
            "license": {"modules_path": "/nonexistent/root/path/modules"}
        }

        loader = PluginBundleLoader()
        # Should not raise, just log error
        loader.initialize()

        # Still marks as initialized even on error
        assert loader._initialized is True


class TestPluginBundleLoaderGetCachedPluginVersion:
    """Tests for _get_cached_plugin_version method."""

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_get_cached_plugin_version_found(self, mock_sessionmaker, mock_db):
        """Test _get_cached_plugin_version returns version when found."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_cache_entry = MagicMock()
        mock_cache_entry.version = "1.0.0"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_cache_entry
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        version = loader._get_cached_plugin_version("health_engine")

        assert version == "1.0.0"

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_get_cached_plugin_version_not_found(self, mock_sessionmaker, mock_db):
        """Test _get_cached_plugin_version returns None when not found."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        version = loader._get_cached_plugin_version("nonexistent")

        assert version is None

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_get_cached_plugin_version_exception(self, mock_sessionmaker, mock_db):
        """Test _get_cached_plugin_version handles exceptions."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Database error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        version = loader._get_cached_plugin_version("health_engine")

        assert version is None


class TestPluginBundleLoaderGetCachedPluginHash:
    """Tests for _get_cached_plugin_hash method."""

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_get_cached_plugin_hash_found(self, mock_sessionmaker, mock_db):
        """Test _get_cached_plugin_hash returns hash when found."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_cache_entry = MagicMock()
        mock_cache_entry.file_hash = "abcdef123456"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_cache_entry
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        hash_result = loader._get_cached_plugin_hash("health_engine")

        assert hash_result == "abcdef123456"


class TestPluginBundleLoaderCheckForPluginUpdates:
    """Tests for check_for_plugin_updates method."""

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_check_for_updates_empty_versions(self, mock_sessionmaker, mock_db):
        """Test check_for_plugin_updates returns empty for empty input."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        updates = loader.check_for_plugin_updates({})

        assert updates == []

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_check_for_updates_none_versions(self, mock_sessionmaker, mock_db):
        """Test check_for_plugin_updates returns empty for None input."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        updates = loader.check_for_plugin_updates(None)

        assert updates == []

    def test_check_for_updates_new_plugin(self):
        """Test check_for_plugin_updates detects new plugins."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "_get_cached_plugin_version", return_value=None):
            server_versions = {"plugins": {"new_module": {"version": "1.0.0"}}}
            updates = loader.check_for_plugin_updates(server_versions)

        assert "new_module" in updates

    def test_check_for_updates_version_mismatch(self):
        """Test check_for_plugin_updates detects version updates."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"):
            server_versions = {"plugins": {"module": {"version": "2.0.0"}}}
            updates = loader.check_for_plugin_updates(server_versions)

        assert "module" in updates

    def test_check_for_updates_hash_mismatch(self):
        """Test check_for_plugin_updates detects hash mismatches."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with (
            patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"),
            patch.object(loader, "_get_cached_plugin_hash", return_value="oldhash"),
        ):
            server_versions = {
                "plugins": {"module": {"version": "1.0.0", "file_hash": "newhash"}}
            }
            updates = loader.check_for_plugin_updates(server_versions)

        assert "module" in updates

    def test_check_for_updates_no_updates_needed(self):
        """Test check_for_plugin_updates returns empty when no updates needed."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with (
            patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"),
            patch.object(loader, "_get_cached_plugin_hash", return_value="samehash"),
        ):
            server_versions = {
                "plugins": {"module": {"version": "1.0.0", "file_hash": "samehash"}}
            }
            updates = loader.check_for_plugin_updates(server_versions)

        assert updates == []


class TestPluginBundleLoaderEnsurePluginAvailable:
    """Tests for ensure_plugin_available method."""

    @pytest.mark.asyncio
    @patch("backend.licensing.plugin_bundle_loader.get_config")
    async def test_ensure_plugin_available_already_exists(
        self, mock_get_config, tmp_path
    ):
        """Test ensure_plugin_available returns True if file exists."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        # Create fake plugin file
        modules_path = tmp_path / "modules"
        modules_path.mkdir()
        plugin_file = modules_path / "health_engine-plugin.iife.js"
        plugin_file.write_text("// plugin code")

        mock_get_config.return_value = {"license": {"modules_path": str(modules_path)}}

        loader = PluginBundleLoader()
        result = await loader.ensure_plugin_available("health_engine")

        assert result is True

    @pytest.mark.asyncio
    @patch("backend.licensing.plugin_bundle_loader.get_config")
    async def test_ensure_plugin_available_downloads(self, mock_get_config, tmp_path):
        """Test ensure_plugin_available downloads if file missing."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        modules_path = tmp_path / "modules"
        modules_path.mkdir()

        mock_get_config.return_value = {
            "license": {
                "modules_path": str(modules_path),
                "phone_home_url": "https://license.example.com",
                "key": "test-key",
            }
        }

        loader = PluginBundleLoader()

        with patch.object(
            loader, "_download_plugin_bundle", new_callable=AsyncMock
        ) as mock_download:
            mock_download.return_value = True
            result = await loader.ensure_plugin_available("health_engine")

        assert result is True
        mock_download.assert_called_once_with("health_engine")


class TestPluginBundleLoaderUpdatePlugins:
    """Tests for update_plugins method."""

    @pytest.mark.asyncio
    async def test_update_plugins_no_updates_needed(self):
        """Test update_plugins returns empty when no updates needed."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "check_for_plugin_updates", return_value=[]):
            result = await loader.update_plugins({"plugins": {}})

        assert result == {}

    @pytest.mark.asyncio
    async def test_update_plugins_downloads_updates(self):
        """Test update_plugins downloads needed updates."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with (
            patch.object(
                loader, "check_for_plugin_updates", return_value=["health_engine"]
            ),
            patch.object(loader, "_remove_cached_plugin"),
            patch.object(
                loader, "_download_plugin_bundle", new_callable=AsyncMock
            ) as mock_download,
        ):
            mock_download.return_value = True
            result = await loader.update_plugins({"plugins": {"health_engine": {}}})

        assert result == {"health_engine": True}
        mock_download.assert_called_once_with("health_engine")

    @pytest.mark.asyncio
    async def test_update_plugins_handles_download_failure(self):
        """Test update_plugins handles download failures."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with (
            patch.object(
                loader, "check_for_plugin_updates", return_value=["failing_plugin"]
            ),
            patch.object(loader, "_remove_cached_plugin"),
            patch.object(
                loader, "_download_plugin_bundle", new_callable=AsyncMock
            ) as mock_download,
        ):
            mock_download.return_value = False
            result = await loader.update_plugins({"plugins": {"failing_plugin": {}}})

        assert result == {"failing_plugin": False}


class TestPluginBundleLoaderSavePluginToCache:
    """Tests for _save_plugin_to_cache method."""

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_save_plugin_to_cache_new_entry(self, mock_sessionmaker, mock_db):
        """Test _save_plugin_to_cache creates new entry."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        loader._save_plugin_to_cache(
            module_code="health_engine",
            version="1.0.0",
            file_path="/path/to/plugin.js",
            file_hash="abc123",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("backend.licensing.plugin_bundle_loader.db_module")
    @patch("backend.licensing.plugin_bundle_loader.sessionmaker")
    def test_save_plugin_to_cache_updates_existing(self, mock_sessionmaker, mock_db):
        """Test _save_plugin_to_cache updates existing entry."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        mock_existing = MagicMock()
        mock_existing.version = "0.9.0"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_existing
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=None)

        mock_session_class = MagicMock(return_value=mock_session)
        mock_sessionmaker.return_value = mock_session_class

        loader = PluginBundleLoader()
        loader._save_plugin_to_cache(
            module_code="health_engine",
            version="1.0.0",
            file_path="/path/to/plugin.js",
            file_hash="abc123",
        )

        assert mock_existing.version == "1.0.0"
        mock_session.commit.assert_called_once()
        mock_session.add.assert_not_called()
