"""
Tests for backend/licensing/public_key.py module.
Tests public key management for Pro+ license verification.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetLicenseServerUrl:
    """Tests for _get_license_server_url function."""

    @patch("backend.licensing.public_key.get_config")
    def test_get_license_server_url_from_config(self, mock_get_config):
        """Test URL from config."""
        from backend.licensing.public_key import _get_license_server_url

        mock_get_config.return_value = {
            "license": {"phone_home_url": "https://custom.server.com"}
        }

        result = _get_license_server_url()

        assert result == "https://custom.server.com"

    @patch("backend.licensing.public_key.get_config")
    def test_get_license_server_url_default(self, mock_get_config):
        """Test default URL when not in config."""
        from backend.licensing.public_key import _get_license_server_url

        mock_get_config.return_value = {}

        result = _get_license_server_url()

        assert result == "https://license.sysmanage.io"


class TestLoadCachedKey:
    """Tests for _load_cached_key function."""

    @patch("backend.licensing.public_key._cache", {"public_key": "cached-key-pem"})
    def test_load_cached_key_from_memory(self):
        """Test returns key from memory cache."""
        from backend.licensing.public_key import _load_cached_key

        result = _load_cached_key()

        assert result == "cached-key-pem"

    @patch("backend.licensing.public_key._cache", {"public_key": None})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_load_cached_key_from_file(self, mock_cache_file):
        """Test loads key from file when not in memory."""
        from backend.licensing.public_key import _load_cached_key

        mock_cache_file.exists.return_value = True
        mock_cache_file.read_text.return_value = "file-key-pem"

        result = _load_cached_key()

        assert result == "file-key-pem"

    @patch("backend.licensing.public_key._cache", {"public_key": None})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_load_cached_key_file_not_exists(self, mock_cache_file):
        """Test returns None when file doesn't exist."""
        from backend.licensing.public_key import _load_cached_key

        mock_cache_file.exists.return_value = False

        result = _load_cached_key()

        assert result is None

    @patch("backend.licensing.public_key._cache", {"public_key": None})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_load_cached_key_file_read_error(self, mock_cache_file):
        """Test handles file read error gracefully."""
        from backend.licensing.public_key import _load_cached_key

        mock_cache_file.exists.return_value = True
        mock_cache_file.read_text.side_effect = Exception("Read error")

        result = _load_cached_key()

        assert result is None


class TestSaveCachedKey:
    """Tests for _save_cached_key function."""

    @patch("backend.licensing.public_key._cache", {"public_key": None})
    @patch("backend.licensing.public_key.CACHE_FILE")
    @patch("backend.licensing.public_key.CACHE_DIR")
    def test_save_cached_key_success(self, mock_cache_dir, mock_cache_file):
        """Test saves key to file and memory."""
        from backend.licensing.public_key import _save_cached_key, _cache

        mock_cache_dir.mkdir = MagicMock()
        mock_cache_file.write_text = MagicMock()

        _save_cached_key("new-key-pem")

        mock_cache_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_cache_file.write_text.assert_called_once_with("new-key-pem")
        assert _cache["public_key"] == "new-key-pem"

    @patch("backend.licensing.public_key._cache", {"public_key": None})
    @patch("backend.licensing.public_key.CACHE_FILE")
    @patch("backend.licensing.public_key.CACHE_DIR")
    def test_save_cached_key_file_write_error(self, mock_cache_dir, mock_cache_file):
        """Test keeps in memory even when file write fails."""
        from backend.licensing.public_key import _save_cached_key, _cache

        mock_cache_dir.mkdir.side_effect = Exception("Permission denied")

        _save_cached_key("error-key-pem")

        # Should still be in memory
        assert _cache["public_key"] == "error-key-pem"


class TestFetchPublicKey:
    """Tests for fetch_public_key function."""

    @patch("backend.licensing.public_key._save_cached_key")
    @patch("backend.licensing.public_key._get_license_server_url")
    @patch("backend.licensing.public_key.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_fetch_public_key_success(
        self, mock_session_class, mock_get_url, mock_save
    ):
        """Test successful key fetch."""
        from backend.licensing.public_key import fetch_public_key

        mock_get_url.return_value = "https://license.example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"public_key": "fetched-key-pem"})

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_response))
        mock_session_class.return_value = AsyncContextManager(mock_session)

        result = await fetch_public_key()

        assert result == "fetched-key-pem"
        mock_save.assert_called_once_with("fetched-key-pem")

    @patch("backend.licensing.public_key._get_license_server_url")
    @patch("backend.licensing.public_key.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_fetch_public_key_empty_response(
        self, mock_session_class, mock_get_url
    ):
        """Test returns None when response is empty."""
        from backend.licensing.public_key import fetch_public_key

        mock_get_url.return_value = "https://license.example.com"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_response))
        mock_session_class.return_value = AsyncContextManager(mock_session)

        result = await fetch_public_key()

        assert result is None

    @patch("backend.licensing.public_key._get_license_server_url")
    @patch("backend.licensing.public_key.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_fetch_public_key_http_error(self, mock_session_class, mock_get_url):
        """Test returns None on HTTP error."""
        from backend.licensing.public_key import fetch_public_key

        mock_get_url.return_value = "https://license.example.com"

        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_response))
        mock_session_class.return_value = AsyncContextManager(mock_session)

        result = await fetch_public_key()

        assert result is None

    @patch("backend.licensing.public_key._get_license_server_url")
    @patch("backend.licensing.public_key.aiohttp.ClientSession")
    @pytest.mark.asyncio
    async def test_fetch_public_key_network_error(
        self, mock_session_class, mock_get_url
    ):
        """Test returns None on network error."""
        import aiohttp

        from backend.licensing.public_key import fetch_public_key

        mock_get_url.return_value = "https://license.example.com"

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError())
        mock_session_class.return_value = AsyncContextManager(mock_session)

        result = await fetch_public_key()

        assert result is None


class TestGetPublicKeyPem:
    """Tests for get_public_key_pem function."""

    @patch("backend.licensing.public_key.fetch_public_key")
    @pytest.mark.asyncio
    async def test_get_public_key_pem_from_server(self, mock_fetch):
        """Test returns key from server."""
        from backend.licensing.public_key import get_public_key_pem

        mock_fetch.return_value = "server-key-pem"

        result = await get_public_key_pem()

        assert result == "server-key-pem"

    @patch("backend.licensing.public_key._load_cached_key")
    @patch("backend.licensing.public_key.fetch_public_key")
    @pytest.mark.asyncio
    async def test_get_public_key_pem_from_cache(self, mock_fetch, mock_load_cached):
        """Test falls back to cache when server unavailable."""
        from backend.licensing.public_key import get_public_key_pem

        mock_fetch.return_value = None
        mock_load_cached.return_value = "cached-key-pem"

        result = await get_public_key_pem()

        assert result == "cached-key-pem"

    @patch("backend.licensing.public_key._load_cached_key")
    @patch("backend.licensing.public_key.fetch_public_key")
    @pytest.mark.asyncio
    async def test_get_public_key_pem_none_available(
        self, mock_fetch, mock_load_cached
    ):
        """Test returns None when no key available."""
        from backend.licensing.public_key import get_public_key_pem

        mock_fetch.return_value = None
        mock_load_cached.return_value = None

        result = await get_public_key_pem()

        assert result is None


class TestGetPublicKeyPemSync:
    """Tests for get_public_key_pem_sync function."""

    @patch("backend.licensing.public_key._load_cached_key")
    def test_get_public_key_pem_sync_returns_cached(self, mock_load_cached):
        """Test returns cached key."""
        from backend.licensing.public_key import get_public_key_pem_sync

        mock_load_cached.return_value = "sync-cached-key"

        result = get_public_key_pem_sync()

        assert result == "sync-cached-key"


class TestGetKeyMetadata:
    """Tests for get_key_metadata function."""

    def test_get_key_metadata(self):
        """Test returns correct key metadata."""
        from backend.licensing.public_key import get_key_metadata

        result = get_key_metadata()

        assert result["algorithm"] == "ES512"
        assert result["curve"] == "P-521"
        assert result["version"] == 1


class TestClearCache:
    """Tests for clear_cache function."""

    @patch("backend.licensing.public_key._cache", {"public_key": "some-key"})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_clear_cache_success(self, mock_cache_file):
        """Test clears memory and file cache."""
        from backend.licensing.public_key import clear_cache, _cache

        mock_cache_file.exists.return_value = True
        mock_cache_file.unlink = MagicMock()

        clear_cache()

        assert _cache["public_key"] is None
        mock_cache_file.unlink.assert_called_once()

    @patch("backend.licensing.public_key._cache", {"public_key": "some-key"})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_clear_cache_file_not_exists(self, mock_cache_file):
        """Test handles missing file gracefully."""
        from backend.licensing.public_key import clear_cache, _cache

        mock_cache_file.exists.return_value = False

        clear_cache()

        assert _cache["public_key"] is None

    @patch("backend.licensing.public_key._cache", {"public_key": "some-key"})
    @patch("backend.licensing.public_key.CACHE_FILE")
    def test_clear_cache_delete_error(self, mock_cache_file):
        """Test handles file delete error gracefully."""
        from backend.licensing.public_key import clear_cache, _cache

        mock_cache_file.exists.return_value = True
        mock_cache_file.unlink.side_effect = Exception("Delete failed")

        clear_cache()

        # Memory cache should still be cleared
        assert _cache["public_key"] is None


# Helper class for async context manager mocking
class AsyncContextManager:
    """Mock async context manager for aiohttp session/response."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass
