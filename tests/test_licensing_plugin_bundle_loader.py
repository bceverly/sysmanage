"""
Tests for backend/licensing/plugin_bundle_loader.py module.
Tests plugin bundle downloading, verification, and caching.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


class TestPluginBundleLoaderInit:
    """Tests for PluginBundleLoader initialization."""

    def test_init_sets_not_initialized(self):
        """Test __init__ sets _initialized to False."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        assert loader._initialized is False


class TestGetModulesPath:
    """Tests for _get_modules_path method."""

    def test_returns_default_path(self):
        """Test returns default path when not configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {}}
        with patch(
            "backend.licensing.plugin_bundle_loader.get_config",
            return_value=mock_config,
        ):
            result = loader._get_modules_path()

        assert result == "/var/lib/sysmanage/modules"

    def test_returns_configured_path(self):
        """Test returns configured path."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {"modules_path": "/custom/path"}}
        with patch(
            "backend.licensing.plugin_bundle_loader.get_config",
            return_value=mock_config,
        ):
            result = loader._get_modules_path()

        assert result == "/custom/path"


class TestGetPluginDownloadUrl:
    """Tests for _get_plugin_download_url method."""

    def test_returns_none_when_no_url_configured(self):
        """Test returns None when no phone_home_url configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {}}
        with patch(
            "backend.licensing.plugin_bundle_loader.get_config",
            return_value=mock_config,
        ):
            result = loader._get_plugin_download_url()

        assert result is None

    def test_returns_constructed_url(self):
        """Test returns constructed download URL."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {"phone_home_url": "https://license.example.com"}}
        with patch(
            "backend.licensing.plugin_bundle_loader.get_config",
            return_value=mock_config,
        ):
            result = loader._get_plugin_download_url()

        assert result == "https://license.example.com/api/v1/modules/download-plugin"

    def test_strips_trailing_slash(self):
        """Test strips trailing slash from URL."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {"phone_home_url": "https://license.example.com/"}}
        with patch(
            "backend.licensing.plugin_bundle_loader.get_config",
            return_value=mock_config,
        ):
            result = loader._get_plugin_download_url()

        assert result == "https://license.example.com/api/v1/modules/download-plugin"


class TestComputeFileHash:
    """Tests for _compute_file_hash method."""

    def test_computes_sha512_hash(self):
        """Test computes SHA-512 hash of file."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader
        import tempfile
        import hashlib

        loader = PluginBundleLoader()

        # Create a test file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            test_data = b"test file content"
            f.write(test_data)
            temp_path = f.name

        try:
            result = loader._compute_file_hash(temp_path)

            # Verify it matches expected hash
            expected = hashlib.sha512(test_data).hexdigest()
            assert result == expected
        finally:
            os.unlink(temp_path)

    def test_hash_is_lowercase_hex(self):
        """Test hash is lowercase hexadecimal."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader
        import tempfile

        loader = PluginBundleLoader()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name

        try:
            result = loader._compute_file_hash(temp_path)

            # SHA-512 produces 128 hex characters
            assert len(result) == 128
            assert all(c in "0123456789abcdef" for c in result)
        finally:
            os.unlink(temp_path)


class TestInitialize:
    """Tests for initialize method."""

    def test_creates_modules_directory(self):
        """Test creates modules directory if not exists."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_path = MagicMock()
        with patch.object(loader, "_get_modules_path", return_value="/test/path"):
            with patch(
                "backend.licensing.plugin_bundle_loader.Path", return_value=mock_path
            ):
                loader.initialize()

        mock_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert loader._initialized is True

    def test_skips_if_already_initialized(self):
        """Test skips initialization if already initialized."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        loader._initialized = True

        mock_path = MagicMock()
        with patch.object(loader, "_get_modules_path", return_value="/test/path"):
            with patch(
                "backend.licensing.plugin_bundle_loader.Path", return_value=mock_path
            ):
                loader.initialize()

        mock_path.mkdir.assert_not_called()

    def test_handles_mkdir_error(self):
        """Test handles directory creation errors gracefully."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_path = MagicMock()
        mock_path.mkdir.side_effect = Exception("Permission denied")

        with patch.object(loader, "_get_modules_path", return_value="/test/path"):
            with patch(
                "backend.licensing.plugin_bundle_loader.Path", return_value=mock_path
            ):
                # Should not raise
                loader.initialize()

        assert loader._initialized is True


class TestGetCachedPluginVersion:
    """Tests for _get_cached_plugin_version method."""

    def test_returns_cached_version(self):
        """Test returns cached version from database."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_entry.version = "1.2.3"
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_entry
        )

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                result = loader._get_cached_plugin_version("test_module")

        assert result == "1.2.3"

    def test_returns_none_when_not_cached(self):
        """Test returns None when plugin not in cache."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                result = loader._get_cached_plugin_version("test_module")

        assert result is None

    def test_handles_database_error(self):
        """Test handles database errors gracefully."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Database error")

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                result = loader._get_cached_plugin_version("test_module")

        assert result is None


class TestGetCachedPluginHash:
    """Tests for _get_cached_plugin_hash method."""

    def test_returns_cached_hash(self):
        """Test returns cached hash from database."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_entry.file_hash = "abc123hash"
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_entry
        )

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                result = loader._get_cached_plugin_hash("test_module")

        assert result == "abc123hash"

    def test_returns_none_when_not_cached(self):
        """Test returns None when plugin not in cache."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                result = loader._get_cached_plugin_hash("test_module")

        assert result is None


class TestCheckForPluginUpdates:
    """Tests for check_for_plugin_updates method."""

    def test_returns_empty_for_empty_input(self):
        """Test returns empty list for empty server versions."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        result = loader.check_for_plugin_updates({})

        assert result == []

    def test_returns_empty_for_none_input(self):
        """Test returns empty list for None server versions."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        result = loader.check_for_plugin_updates(None)

        assert result == []

    def test_detects_new_plugin(self):
        """Test detects new plugin (not cached)."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        server_versions = {
            "plugins": {"new_module": {"version": "1.0.0", "file_hash": "abc123"}}
        }

        with patch.object(loader, "_get_cached_plugin_version", return_value=None):
            result = loader.check_for_plugin_updates(server_versions)

        assert "new_module" in result

    def test_detects_version_update(self):
        """Test detects version update."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        server_versions = {
            "plugins": {"module": {"version": "2.0.0", "file_hash": "abc123"}}
        }

        with patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"):
            result = loader.check_for_plugin_updates(server_versions)

        assert "module" in result

    def test_detects_hash_mismatch(self):
        """Test detects rebuild (hash mismatch)."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        server_versions = {
            "plugins": {"module": {"version": "1.0.0", "file_hash": "newhash"}}
        }

        with patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"):
            with patch.object(
                loader, "_get_cached_plugin_hash", return_value="oldhash"
            ):
                result = loader.check_for_plugin_updates(server_versions)

        assert "module" in result

    def test_no_update_when_current(self):
        """Test no update when already current."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        server_versions = {
            "plugins": {"module": {"version": "1.0.0", "file_hash": "samehash"}}
        }

        with patch.object(loader, "_get_cached_plugin_version", return_value="1.0.0"):
            with patch.object(
                loader, "_get_cached_plugin_hash", return_value="samehash"
            ):
                result = loader.check_for_plugin_updates(server_versions)

        assert "module" not in result


class TestEnsurePluginAvailable:
    """Tests for ensure_plugin_available method."""

    @pytest.mark.asyncio
    async def test_returns_true_if_file_exists(self):
        """Test returns True if plugin file already exists."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        loader._initialized = True

        with patch.object(loader, "_get_modules_path", return_value="/test/path"):
            with patch("os.path.exists", return_value=True):
                result = await loader.ensure_plugin_available("test_module")

        assert result is True

    @pytest.mark.asyncio
    async def test_downloads_if_not_exists(self):
        """Test downloads plugin if file doesn't exist."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        loader._initialized = True

        with patch.object(loader, "_get_modules_path", return_value="/test/path"):
            with patch("os.path.exists", return_value=False):
                with patch.object(
                    loader, "_download_plugin_bundle", new=AsyncMock(return_value=True)
                ):
                    result = await loader.ensure_plugin_available("test_module")

        assert result is True

    @pytest.mark.asyncio
    async def test_initializes_if_not_initialized(self):
        """Test initializes loader if not already initialized."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()
        loader._initialized = False

        with patch.object(loader, "initialize") as mock_init:
            with patch.object(loader, "_get_modules_path", return_value="/test/path"):
                with patch("os.path.exists", return_value=True):
                    await loader.ensure_plugin_available("test_module")

        mock_init.assert_called_once()


class TestDownloadPluginBundle:
    """Tests for _download_plugin_bundle method."""

    @pytest.mark.asyncio
    async def test_returns_false_if_no_download_url(self):
        """Test returns False if no download URL configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "_get_plugin_download_url", return_value=None):
            result = await loader._download_plugin_bundle("test_module")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_if_no_license_key(self):
        """Test returns False if no license key configured."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_config = {"license": {}}
        with patch.object(
            loader,
            "_get_plugin_download_url",
            return_value="https://example.com/download",
        ):
            with patch(
                "backend.licensing.plugin_bundle_loader.get_config",
                return_value=mock_config,
            ):
                result = await loader._download_plugin_bundle("test_module")

        assert result is False


class TestUpdatePlugins:
    """Tests for update_plugins method."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_updates(self):
        """Test returns empty dict when no updates needed."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "check_for_plugin_updates", return_value=[]):
            result = await loader.update_plugins({})

        assert result == {}

    @pytest.mark.asyncio
    async def test_updates_available_plugins(self):
        """Test updates plugins when updates available."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        with patch.object(loader, "check_for_plugin_updates", return_value=["module1"]):
            with patch.object(loader, "_remove_cached_plugin"):
                with patch.object(
                    loader, "_download_plugin_bundle", new=AsyncMock(return_value=True)
                ):
                    result = await loader.update_plugins({})

        assert result == {"module1": True}


class TestRemoveCachedPlugin:
    """Tests for _remove_cached_plugin method."""

    def test_removes_file_and_db_entry(self):
        """Test removes both file and database entry."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_entry.file_path = "/test/file.js"
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_entry
        ]

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove") as mock_remove:
                        loader._remove_cached_plugin("test_module")

        mock_remove.assert_called_once_with("/test/file.js")
        mock_session.delete.assert_called_once_with(mock_entry)
        mock_session.commit.assert_called_once()


class TestSavePluginToCache:
    """Tests for _save_plugin_to_cache method."""

    def test_creates_new_entry(self):
        """Test creates new cache entry if not exists."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                loader._save_plugin_to_cache(
                    module_code="test_module",
                    version="1.0.0",
                    file_path="/test/path.js",
                    file_hash="abc123",
                )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_updates_existing_entry(self):
        """Test updates existing cache entry."""
        from backend.licensing.plugin_bundle_loader import PluginBundleLoader

        loader = PluginBundleLoader()

        mock_session = MagicMock()
        mock_entry = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_entry
        )

        with patch(
            "backend.licensing.plugin_bundle_loader.sessionmaker"
        ) as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )
            with patch("backend.licensing.plugin_bundle_loader.db_module.get_engine"):
                loader._save_plugin_to_cache(
                    module_code="test_module",
                    version="2.0.0",
                    file_path="/new/path.js",
                    file_hash="newhash",
                )

        assert mock_entry.version == "2.0.0"
        assert mock_entry.file_path == "/new/path.js"
        assert mock_entry.file_hash == "newhash"
        mock_session.commit.assert_called_once()


class TestModuleConstants:
    """Tests for module constants."""

    def test_default_modules_path(self):
        """Test DEFAULT_MODULES_PATH constant."""
        from backend.licensing.plugin_bundle_loader import DEFAULT_MODULES_PATH

        assert DEFAULT_MODULES_PATH == "/var/lib/sysmanage/modules"

    def test_download_timeout(self):
        """Test DOWNLOAD_TIMEOUT constant."""
        from backend.licensing.plugin_bundle_loader import DOWNLOAD_TIMEOUT

        assert DOWNLOAD_TIMEOUT == 300
