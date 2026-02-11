"""
Tests for backend/licensing/module_loader.py module.
Tests Pro+ Cython module loading functionality.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
import os


class TestModuleLoaderProperties:
    """Tests for ModuleLoader properties."""

    def test_loaded_modules_initially_empty(self):
        """Test that loaded_modules is empty initially."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        assert loader.loaded_modules == {}

    def test_loaded_modules_returns_copy(self):
        """Test that loaded_modules returns a copy."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._loaded_modules["test"] = MagicMock()

        modules = loader.loaded_modules
        modules["new"] = MagicMock()

        assert "new" not in loader._loaded_modules


class TestModuleLoaderConfig:
    """Tests for ModuleLoader configuration methods."""

    def test_get_modules_path_default(self):
        """Test _get_modules_path returns default."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_modules_path()

        assert result == "/var/lib/sysmanage/modules"

    def test_get_modules_path_configured(self):
        """Test _get_modules_path returns configured value."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"modules_path": "/custom/modules"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_modules_path()

        assert result == "/custom/modules"

    def test_get_download_url_none(self):
        """Test _get_download_url returns None without phone_home_url."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_download_url()

        assert result is None

    def test_get_download_url_configured(self):
        """Test _get_download_url returns URL with path."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"phone_home_url": "https://license.example.com"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_download_url()

        assert result == "https://license.example.com/api/v1/modules/download"

    def test_get_versions_url_none(self):
        """Test _get_versions_url returns None without phone_home_url."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_versions_url()

        assert result is None

    def test_get_versions_url_configured(self):
        """Test _get_versions_url returns URL with path."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"phone_home_url": "https://license.example.com/"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = loader._get_versions_url()

        assert result == "https://license.example.com/api/v1/modules/versions"


class TestModuleLoaderPlatformInfo:
    """Tests for ModuleLoader platform info."""

    def test_get_platform_info_returns_dict(self):
        """Test _get_platform_info returns platform dict."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        result = loader._get_platform_info()

        assert "platform" in result
        assert "architecture" in result
        assert "python_version" in result

    def test_get_platform_info_normalizes_arch(self):
        """Test _get_platform_info normalizes architecture."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with patch("platform.machine", return_value="x86_64"):
            result = loader._get_platform_info()
            assert result["architecture"] == "x86_64"

        with patch("platform.machine", return_value="amd64"):
            result = loader._get_platform_info()
            assert result["architecture"] == "x86_64"

        with patch("platform.machine", return_value="aarch64"):
            result = loader._get_platform_info()
            assert result["architecture"] == "aarch64"

        with patch("platform.machine", return_value="arm64"):
            result = loader._get_platform_info()
            assert result["architecture"] == "aarch64"


class TestModuleLoaderFileHash:
    """Tests for ModuleLoader file hash computation."""

    def test_compute_file_hash(self):
        """Test _compute_file_hash returns SHA-512 hash."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            result = loader._compute_file_hash(temp_path)
            assert len(result) == 128  # SHA-512 hex length
        finally:
            os.unlink(temp_path)


class TestModuleLoaderInitialize:
    """Tests for ModuleLoader.initialize method."""

    def test_initialize_creates_directory(self):
        """Test initialize creates modules directory."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"modules_path": "/tmp/test_modules"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            with patch.object(loader._plugin_loader, "initialize"):
                loader.initialize()

        assert loader._initialized is True

    def test_initialize_already_initialized(self):
        """Test initialize returns early if already initialized."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True

        # Should return without doing anything
        loader.initialize()

    def test_initialize_handles_directory_error(self):
        """Test initialize handles directory creation error."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"modules_path": "/invalid/path/test"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
                with patch.object(loader._plugin_loader, "initialize"):
                    loader.initialize()

        # Should still set initialized
        assert loader._initialized is True


class TestModuleLoaderIsLoaded:
    """Tests for ModuleLoader.is_module_loaded method."""

    def test_is_module_loaded_false(self):
        """Test is_module_loaded returns False for unloaded module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        assert loader.is_module_loaded("test_module") is False

    def test_is_module_loaded_true(self):
        """Test is_module_loaded returns True for loaded module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._loaded_modules["test_module"] = MagicMock()

        assert loader.is_module_loaded("test_module") is True


class TestModuleLoaderGetModule:
    """Tests for ModuleLoader.get_module method."""

    def test_get_module_not_loaded(self):
        """Test get_module returns None for unloaded module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        assert loader.get_module("test_module") is None

    def test_get_module_loaded(self):
        """Test get_module returns module object."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock()
        loader._loaded_modules["test_module"] = mock_module

        result = loader.get_module("test_module")
        assert result is mock_module


class TestModuleLoaderUnload:
    """Tests for ModuleLoader.unload_module method."""

    def test_unload_module_not_loaded(self):
        """Test unload_module returns False for unloaded module."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        result = loader.unload_module("test_module")
        assert result is False

    def test_unload_module_success(self):
        """Test unload_module removes module."""
        from backend.licensing.module_loader import ModuleLoader
        import sys

        loader = ModuleLoader()
        mock_module = MagicMock()
        loader._loaded_modules["test_unload"] = mock_module
        sys.modules["test_unload"] = mock_module

        result = loader.unload_module("test_unload")

        assert result is True
        assert "test_unload" not in loader._loaded_modules
        assert "test_unload" not in sys.modules


class TestModuleLoaderGetInfo:
    """Tests for ModuleLoader.get_loaded_module_info method."""

    def test_get_loaded_module_info_empty(self):
        """Test get_loaded_module_info with no modules."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        result = loader.get_loaded_module_info()
        assert result == {}

    def test_get_loaded_module_info_with_modules(self):
        """Test get_loaded_module_info with loaded modules."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_module = MagicMock()
        mock_module.__version__ = "1.0.0"
        mock_module.__file__ = "/path/to/module.so"
        loader._loaded_modules["test_module"] = mock_module

        result = loader.get_loaded_module_info()

        assert "test_module" in result
        assert result["test_module"]["loaded"] is True
        assert result["test_module"]["version"] == "1.0.0"
        assert result["test_module"]["file"] == "/path/to/module.so"


class TestModuleLoaderEnsureAvailable:
    """Tests for ModuleLoader.ensure_module_available method."""

    @pytest.mark.asyncio
    async def test_ensure_module_available_proplus_core(self):
        """Test ensure_module_available for proplus_core skips Cython loading."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True

        with patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=True)
        ):
            result = await loader.ensure_module_available("proplus_core")

        assert result is True


class TestModuleLoaderQueryVersions:
    """Tests for ModuleLoader.query_server_versions method."""

    @pytest.mark.asyncio
    async def test_query_server_versions_no_url(self):
        """Test query_server_versions returns empty without URL."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = await loader.query_server_versions()

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_server_versions_no_license_key(self):
        """Test query_server_versions returns empty without license key."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_config = {"license": {"phone_home_url": "https://example.com"}}

        with patch(
            "backend.licensing.module_loader.get_config", return_value=mock_config
        ):
            result = await loader.query_server_versions()

        assert result == {}


class TestModuleLoaderCheckUpdates:
    """Tests for ModuleLoader.check_for_updates method."""

    @pytest.mark.asyncio
    async def test_check_for_updates_no_server_data(self):
        """Test check_for_updates returns empty without server data."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value={})
        ):
            result = await loader.check_for_updates()

        assert result == []

    @pytest.mark.asyncio
    async def test_check_for_updates_new_module(self):
        """Test check_for_updates detects new modules."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        server_data = {
            "modules": {"new_module": {"version": "1.0.0", "file_hash": "abc123"}}
        }

        with patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value=server_data)
        ):
            with patch.object(loader, "_get_cached_module_version", return_value=None):
                result = await loader.check_for_updates()

        assert "new_module" in result


class TestModuleLoaderLoadFromPath:
    """Tests for ModuleLoader._load_module_from_path method."""

    def test_load_module_from_path_no_spec(self):
        """Test _load_module_from_path handles missing spec."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with patch("importlib.util.spec_from_file_location", return_value=None):
            result = loader._load_module_from_path("test", "/path/to/module.so")

        assert result is False

    def test_load_module_from_path_exception(self):
        """Test _load_module_from_path handles exceptions."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        with patch(
            "importlib.util.spec_from_file_location",
            side_effect=Exception("Load error"),
        ):
            result = loader._load_module_from_path("test", "/path/to/module.so")

        assert result is False


class TestModuleLoaderGlobal:
    """Tests for global module_loader instance."""

    def test_module_loader_instance_exists(self):
        """Test that global module_loader instance exists."""
        from backend.licensing.module_loader import module_loader

        assert module_loader is not None

    def test_module_loader_is_module_loader(self):
        """Test that global instance is ModuleLoader type."""
        from backend.licensing.module_loader import module_loader, ModuleLoader

        assert isinstance(module_loader, ModuleLoader)


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


class TestModuleLoaderCachedVersion:
    """Tests for ModuleLoader cached version methods."""

    def test_get_cached_module_version_none(self):
        """Test _get_cached_module_version returns None when not cached."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )

        with patch("backend.licensing.module_loader.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.module_loader.db_module.get_engine"):
                result = loader._get_cached_module_version("test_module")

        assert result is None

    def test_get_cached_module_version_found(self):
        """Test _get_cached_module_version returns version when cached."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        mock_entry = MagicMock()
        mock_entry.version = "2.1.0"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            mock_entry
        )

        with patch("backend.licensing.module_loader.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.module_loader.db_module.get_engine"):
                result = loader._get_cached_module_version("test_module")

        assert result == "2.1.0"

    def test_get_cached_module_hash_exception(self):
        """Test _get_cached_module_hash handles exceptions."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        mock_session = MagicMock()
        mock_session.query.side_effect = Exception("Database error")

        with patch("backend.licensing.module_loader.sessionmaker") as mock_sessionmaker:
            mock_sessionmaker.return_value.return_value.__enter__ = MagicMock(
                return_value=mock_session
            )
            mock_sessionmaker.return_value.return_value.__exit__ = MagicMock(
                return_value=None
            )

            with patch("backend.licensing.module_loader.db_module.get_engine"):
                result = loader._get_cached_module_hash("test_module")

        assert result is None
