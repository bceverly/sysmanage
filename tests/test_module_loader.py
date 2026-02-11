"""
Tests for backend/licensing/module_loader.py module.
Tests Pro+ Cython module loader functionality.
"""

import platform
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestModuleLoaderConstants:
    """Tests for module constants."""

    def test_default_modules_path(self):
        """Test DEFAULT_MODULES_PATH constant."""
        from backend.licensing.module_loader import DEFAULT_MODULES_PATH

        assert DEFAULT_MODULES_PATH == "/var/lib/sysmanage/modules"

    def test_download_timeout(self):
        """Test DOWNLOAD_TIMEOUT constant."""
        from backend.licensing.module_loader import DOWNLOAD_TIMEOUT

        assert DOWNLOAD_TIMEOUT == 300

    def test_version_check_timeout(self):
        """Test VERSION_CHECK_TIMEOUT constant."""
        from backend.licensing.module_loader import VERSION_CHECK_TIMEOUT

        assert VERSION_CHECK_TIMEOUT == 30


class TestModuleLoaderInit:
    """Tests for ModuleLoader initialization."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_init_sets_defaults(self, mock_plugin_loader):
        """Test initialization sets default values."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        assert loader._loaded_modules == {}
        assert loader._initialized is False

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_loaded_modules_property_returns_copy(self, mock_plugin_loader):
        """Test loaded_modules property returns a copy."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._loaded_modules["test"] = MagicMock()

        modules = loader.loaded_modules
        assert "test" in modules

        # Modifying returned dict shouldn't affect internal state
        modules["new"] = "value"
        assert "new" not in loader._loaded_modules


class TestModuleLoaderGetModulesPath:
    """Tests for _get_modules_path method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_modules_path_default(self, mock_get_config, mock_plugin_loader):
        """Test _get_modules_path returns default when not configured."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {}

        loader = ModuleLoader()
        path = loader._get_modules_path()

        assert path == "/var/lib/sysmanage/modules"

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_modules_path_configured(self, mock_get_config, mock_plugin_loader):
        """Test _get_modules_path returns configured value."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {"license": {"modules_path": "/custom/modules"}}

        loader = ModuleLoader()
        path = loader._get_modules_path()

        assert path == "/custom/modules"


class TestModuleLoaderGetDownloadUrl:
    """Tests for _get_download_url method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_download_url_not_configured(self, mock_get_config, mock_plugin_loader):
        """Test _get_download_url returns None when not configured."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {"license": {}}

        loader = ModuleLoader()
        url = loader._get_download_url()

        assert url is None

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_download_url_configured(self, mock_get_config, mock_plugin_loader):
        """Test _get_download_url returns proper URL."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://license.example.com"}
        }

        loader = ModuleLoader()
        url = loader._get_download_url()

        assert url == "https://license.example.com/api/v1/modules/download"


class TestModuleLoaderGetVersionsUrl:
    """Tests for _get_versions_url method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_versions_url_not_configured(self, mock_get_config, mock_plugin_loader):
        """Test _get_versions_url returns None when not configured."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {"license": {}}

        loader = ModuleLoader()
        url = loader._get_versions_url()

        assert url is None

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_get_versions_url_configured(self, mock_get_config, mock_plugin_loader):
        """Test _get_versions_url returns proper URL."""
        from backend.licensing.module_loader import ModuleLoader

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://license.example.com/"}
        }

        loader = ModuleLoader()
        url = loader._get_versions_url()

        assert url == "https://license.example.com/api/v1/modules/versions"


class TestModuleLoaderGetPlatformInfo:
    """Tests for _get_platform_info method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_platform_info_returns_dict(self, mock_plugin_loader):
        """Test _get_platform_info returns expected keys."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        info = loader._get_platform_info()

        assert "platform" in info
        assert "architecture" in info
        assert "python_version" in info

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_platform_info_correct_python_version(self, mock_plugin_loader):
        """Test _get_platform_info returns correct Python version."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        info = loader._get_platform_info()

        expected_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert info["python_version"] == expected_version

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.platform")
    def test_get_platform_info_normalizes_x86_64(
        self, mock_platform, mock_plugin_loader
    ):
        """Test _get_platform_info normalizes x86_64 architecture."""
        from backend.licensing.module_loader import ModuleLoader

        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "x86_64"

        loader = ModuleLoader()
        info = loader._get_platform_info()

        assert info["architecture"] == "x86_64"

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.platform")
    def test_get_platform_info_normalizes_amd64(
        self, mock_platform, mock_plugin_loader
    ):
        """Test _get_platform_info normalizes amd64 to x86_64."""
        from backend.licensing.module_loader import ModuleLoader

        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "amd64"

        loader = ModuleLoader()
        info = loader._get_platform_info()

        assert info["architecture"] == "x86_64"

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.platform")
    def test_get_platform_info_normalizes_arm64(
        self, mock_platform, mock_plugin_loader
    ):
        """Test _get_platform_info normalizes arm64 to aarch64."""
        from backend.licensing.module_loader import ModuleLoader

        mock_platform.system.return_value = "Linux"
        mock_platform.machine.return_value = "arm64"

        loader = ModuleLoader()
        info = loader._get_platform_info()

        assert info["architecture"] == "aarch64"


class TestModuleLoaderComputeFileHash:
    """Tests for _compute_file_hash method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_compute_file_hash(self, mock_plugin_loader, tmp_path):
        """Test _compute_file_hash computes correct SHA-512 hash."""
        from backend.licensing.module_loader import ModuleLoader

        # Create a test file
        test_file = tmp_path / "test.so"
        test_file.write_bytes(b"test module content")

        loader = ModuleLoader()
        hash_result = loader._compute_file_hash(str(test_file))

        # SHA-512 hash is 128 hex characters
        assert len(hash_result) == 128


class TestModuleLoaderInitialize:
    """Tests for initialize method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    @patch("backend.licensing.module_loader.get_config")
    def test_initialize_creates_directory(
        self, mock_get_config, mock_plugin_loader_class, tmp_path
    ):
        """Test initialize creates modules directory."""
        from backend.licensing.module_loader import ModuleLoader

        modules_dir = tmp_path / "modules"
        mock_get_config.return_value = {"license": {"modules_path": str(modules_dir)}}

        mock_plugin_loader = MagicMock()
        mock_plugin_loader_class.return_value = mock_plugin_loader

        loader = ModuleLoader()
        loader.initialize()

        assert modules_dir.exists()
        assert loader._initialized is True
        mock_plugin_loader.initialize.assert_called_once()

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_initialize_skips_if_already_initialized(self, mock_plugin_loader_class):
        """Test initialize skips if already initialized."""
        from backend.licensing.module_loader import ModuleLoader

        mock_plugin_loader = MagicMock()
        mock_plugin_loader_class.return_value = mock_plugin_loader

        loader = ModuleLoader()
        loader._initialized = True

        loader.initialize()

        # Plugin loader's initialize shouldn't be called again
        mock_plugin_loader.initialize.assert_not_called()


class TestModuleLoaderIsModuleLoaded:
    """Tests for is_module_loaded method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_is_module_loaded_returns_true(self, mock_plugin_loader):
        """Test is_module_loaded returns True when module is loaded."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._loaded_modules["test_module"] = MagicMock()

        assert loader.is_module_loaded("test_module") is True

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_is_module_loaded_returns_false(self, mock_plugin_loader):
        """Test is_module_loaded returns False when module not loaded."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        assert loader.is_module_loaded("nonexistent") is False


class TestModuleLoaderGetModule:
    """Tests for get_module method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_module_returns_module(self, mock_plugin_loader):
        """Test get_module returns loaded module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock()
        loader._loaded_modules["test_module"] = mock_module

        result = loader.get_module("test_module")

        assert result == mock_module

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_module_returns_none_when_not_loaded(self, mock_plugin_loader):
        """Test get_module returns None when module not loaded."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        result = loader.get_module("nonexistent")

        assert result is None


class TestModuleLoaderUnloadModule:
    """Tests for unload_module method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_unload_module_success(self, mock_plugin_loader):
        """Test unload_module successfully unloads module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock()
        loader._loaded_modules["test_module"] = mock_module

        result = loader.unload_module("test_module")

        assert result is True
        assert "test_module" not in loader._loaded_modules

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_unload_module_not_loaded(self, mock_plugin_loader):
        """Test unload_module returns False when module not loaded."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        result = loader.unload_module("nonexistent")

        assert result is False


class TestModuleLoaderGetLoadedModuleInfo:
    """Tests for get_loaded_module_info method."""

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_loaded_module_info_returns_info(self, mock_plugin_loader):
        """Test get_loaded_module_info returns module information."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock()
        mock_module.__version__ = "1.2.3"
        mock_module.__file__ = "/path/to/module.so"
        loader._loaded_modules["test_module"] = mock_module

        info = loader.get_loaded_module_info()

        assert "test_module" in info
        assert info["test_module"]["loaded"] is True
        assert info["test_module"]["version"] == "1.2.3"
        assert info["test_module"]["file"] == "/path/to/module.so"

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_loaded_module_info_handles_missing_attrs(self, mock_plugin_loader):
        """Test get_loaded_module_info handles missing module attributes."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock(spec=[])  # No __version__ or __file__
        loader._loaded_modules["test_module"] = mock_module

        info = loader.get_loaded_module_info()

        assert info["test_module"]["version"] == "unknown"
        assert info["test_module"]["file"] == "unknown"

    @patch("backend.licensing.module_loader.PluginBundleLoader")
    def test_get_loaded_module_info_empty(self, mock_plugin_loader):
        """Test get_loaded_module_info returns empty dict when no modules."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        info = loader.get_loaded_module_info()

        assert info == {}


class TestModuleLoaderEnsureModuleAvailable:
    """Tests for ensure_module_available method."""

    @pytest.mark.asyncio
    @patch("backend.licensing.module_loader.PluginBundleLoader")
    async def test_ensure_module_available_proplus_core(self, mock_plugin_loader_class):
        """Test ensure_module_available handles proplus_core specially."""
        from backend.licensing.module_loader import ModuleLoader

        mock_plugin_loader = MagicMock()
        mock_plugin_loader.ensure_plugin_available = AsyncMock(return_value=True)
        mock_plugin_loader_class.return_value = mock_plugin_loader

        loader = ModuleLoader()
        loader._initialized = True

        result = await loader.ensure_module_available("proplus_core")

        assert result is True
        mock_plugin_loader.ensure_plugin_available.assert_called_once_with(
            "proplus_core"
        )


class TestModuleLoaderCheckForUpdates:
    """Tests for check_for_updates method."""

    @pytest.mark.asyncio
    @patch("backend.licensing.module_loader.PluginBundleLoader")
    async def test_check_for_updates_no_server_data(self, mock_plugin_loader):
        """Test check_for_updates returns empty when no server data."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with patch.object(
            loader, "query_server_versions", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = {}
            updates = await loader.check_for_updates()

        assert updates == []

    @pytest.mark.asyncio
    @patch("backend.licensing.module_loader.PluginBundleLoader")
    async def test_check_for_updates_new_module(self, mock_plugin_loader):
        """Test check_for_updates detects new modules."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with (
            patch.object(
                loader, "query_server_versions", new_callable=AsyncMock
            ) as mock_query,
            patch.object(loader, "_get_cached_module_version", return_value=None),
        ):
            mock_query.return_value = {
                "modules": {"new_module": {"version": "1.0.0", "file_hash": "abc"}}
            }
            updates = await loader.check_for_updates()

        assert "new_module" in updates

    @pytest.mark.asyncio
    @patch("backend.licensing.module_loader.PluginBundleLoader")
    async def test_check_for_updates_version_mismatch(self, mock_plugin_loader):
        """Test check_for_updates detects version updates."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with (
            patch.object(
                loader, "query_server_versions", new_callable=AsyncMock
            ) as mock_query,
            patch.object(loader, "_get_cached_module_version", return_value="1.0.0"),
        ):
            mock_query.return_value = {
                "modules": {"module": {"version": "2.0.0", "file_hash": "abc"}}
            }
            updates = await loader.check_for_updates()

        assert "module" in updates


class TestModuleLoaderGlobalInstance:
    """Tests for global module_loader instance."""

    def test_global_instance_exists(self):
        """Test that global module_loader instance exists."""
        from backend.licensing.module_loader import module_loader

        assert module_loader is not None

    def test_global_instance_type(self):
        """Test that global instance is correct type."""
        from backend.licensing.module_loader import ModuleLoader, module_loader

        assert isinstance(module_loader, ModuleLoader)
