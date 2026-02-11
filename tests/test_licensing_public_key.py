"""
Tests for backend/licensing/public_key.py module.
Tests public key fetching, caching, and management.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


class TestGetLicenseServerUrl:
    """Tests for _get_license_server_url function."""

    def test_returns_default_url(self):
        """Test returns default URL when not configured."""
        from backend.licensing.public_key import _get_license_server_url

        mock_config = {"license": {}}
        with patch("backend.licensing.public_key.get_config", return_value=mock_config):
            result = _get_license_server_url()

        assert result == "https://license.sysmanage.io"

    def test_returns_configured_url(self):
        """Test returns configured URL."""
        from backend.licensing.public_key import _get_license_server_url

        mock_config = {"license": {"phone_home_url": "https://custom.example.com"}}
        with patch("backend.licensing.public_key.get_config", return_value=mock_config):
            result = _get_license_server_url()

        assert result == "https://custom.example.com"


class TestLoadCachedKey:
    """Tests for _load_cached_key function."""

    def test_returns_memory_cached_key(self):
        """Test returns key from memory cache."""
        from backend.licensing import public_key

        # Set up memory cache
        public_key._cache["public_key"] = "cached-key-data"
        try:
            result = public_key._load_cached_key()
            assert result == "cached-key-data"
        finally:
            # Clean up
            public_key._cache["public_key"] = None

    def test_returns_none_when_no_cache(self):
        """Test returns None when no cache available."""
        from backend.licensing import public_key

        # Clear memory cache
        public_key._cache["public_key"] = None

        mock_file = MagicMock()
        mock_file.exists.return_value = False

        with patch.object(public_key, "CACHE_FILE", mock_file):
            result = public_key._load_cached_key()

        assert result is None

    def test_loads_from_file_when_memory_empty(self):
        """Test loads from file when memory cache is empty."""
        from backend.licensing import public_key

        # Clear memory cache
        public_key._cache["public_key"] = None

        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "file-key-data"

        with patch.object(public_key, "CACHE_FILE", mock_file):
            result = public_key._load_cached_key()

        assert result == "file-key-data"
        # Clean up memory cache
        public_key._cache["public_key"] = None

    def test_handles_file_read_error(self):
        """Test handles file read errors gracefully."""
        from backend.licensing import public_key

        # Clear memory cache
        public_key._cache["public_key"] = None

        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.read_text.side_effect = Exception("Read error")

        with patch.object(public_key, "CACHE_FILE", mock_file):
            result = public_key._load_cached_key()

        assert result is None


class TestSaveCachedKey:
    """Tests for _save_cached_key function."""

    def test_saves_key_to_memory(self):
        """Test saves key to memory cache."""
        from backend.licensing import public_key

        mock_dir = MagicMock()
        mock_file = MagicMock()

        with patch.object(public_key, "CACHE_DIR", mock_dir):
            with patch.object(public_key, "CACHE_FILE", mock_file):
                public_key._save_cached_key("new-key-data")

        assert public_key._cache["public_key"] == "new-key-data"
        # Clean up
        public_key._cache["public_key"] = None

    def test_handles_write_error(self):
        """Test handles write errors gracefully."""
        from backend.licensing import public_key

        mock_dir = MagicMock()
        mock_dir.mkdir.side_effect = Exception("Permission denied")

        with patch.object(public_key, "CACHE_DIR", mock_dir):
            # Should not raise
            public_key._save_cached_key("error-key-data")

        # Should still be in memory cache
        assert public_key._cache["public_key"] == "error-key-data"
        # Clean up
        public_key._cache["public_key"] = None


class TestFetchPublicKey:
    """Tests for fetch_public_key async function."""

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Test successful public key fetch."""
        from backend.licensing import public_key

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"public_key": "fetched-key-data"})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch.object(
                public_key,
                "_get_license_server_url",
                return_value="https://example.com",
            ):
                with patch.object(public_key, "_save_cached_key"):
                    result = await public_key.fetch_public_key()

        assert result == "fetched-key-data"

    @pytest.mark.asyncio
    async def test_fetch_http_error(self):
        """Test handles HTTP error response."""
        from backend.licensing import public_key

        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch.object(
                public_key,
                "_get_license_server_url",
                return_value="https://example.com",
            ):
                result = await public_key.fetch_public_key()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_empty_key(self):
        """Test handles empty public key in response."""
        from backend.licensing import public_key

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"public_key": None})

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch.object(
                public_key,
                "_get_license_server_url",
                return_value="https://example.com",
            ):
                result = await public_key.fetch_public_key()

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_network_error(self):
        """Test handles network errors."""
        import aiohttp
        from backend.licensing import public_key

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session_class.side_effect = aiohttp.ClientError("Network error")
            with patch.object(
                public_key,
                "_get_license_server_url",
                return_value="https://example.com",
            ):
                result = await public_key.fetch_public_key()

        assert result is None


class TestGetPublicKeyPem:
    """Tests for get_public_key_pem async function."""

    @pytest.mark.asyncio
    async def test_returns_fetched_key(self):
        """Test returns freshly fetched key."""
        from backend.licensing import public_key

        with patch.object(
            public_key, "fetch_public_key", new=AsyncMock(return_value="fresh-key")
        ):
            result = await public_key.get_public_key_pem()

        assert result == "fresh-key"

    @pytest.mark.asyncio
    async def test_falls_back_to_cache(self):
        """Test falls back to cached key when fetch fails."""
        from backend.licensing import public_key

        with patch.object(
            public_key, "fetch_public_key", new=AsyncMock(return_value=None)
        ):
            with patch.object(
                public_key, "_load_cached_key", return_value="cached-key"
            ):
                result = await public_key.get_public_key_pem()

        assert result == "cached-key"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_key_available(self):
        """Test returns None when no key available."""
        from backend.licensing import public_key

        with patch.object(
            public_key, "fetch_public_key", new=AsyncMock(return_value=None)
        ):
            with patch.object(public_key, "_load_cached_key", return_value=None):
                result = await public_key.get_public_key_pem()

        assert result is None


class TestGetPublicKeyPemSync:
    """Tests for get_public_key_pem_sync function."""

    def test_returns_cached_key(self):
        """Test returns cached key synchronously."""
        from backend.licensing import public_key

        with patch.object(
            public_key, "_load_cached_key", return_value="sync-cached-key"
        ):
            result = public_key.get_public_key_pem_sync()

        assert result == "sync-cached-key"

    def test_returns_none_when_no_cache(self):
        """Test returns None when no cache available."""
        from backend.licensing import public_key

        with patch.object(public_key, "_load_cached_key", return_value=None):
            result = public_key.get_public_key_pem_sync()

        assert result is None


class TestGetKeyMetadata:
    """Tests for get_key_metadata function."""

    def test_returns_metadata_dict(self):
        """Test returns metadata dictionary."""
        from backend.licensing.public_key import get_key_metadata

        result = get_key_metadata()

        assert isinstance(result, dict)
        assert "algorithm" in result
        assert "curve" in result
        assert "version" in result

    def test_returns_correct_algorithm(self):
        """Test returns correct algorithm."""
        from backend.licensing.public_key import get_key_metadata

        result = get_key_metadata()

        assert result["algorithm"] == "ES512"

    def test_returns_correct_curve(self):
        """Test returns correct curve."""
        from backend.licensing.public_key import get_key_metadata

        result = get_key_metadata()

        assert result["curve"] == "P-521"

    def test_returns_correct_version(self):
        """Test returns correct version."""
        from backend.licensing.public_key import get_key_metadata

        result = get_key_metadata()

        assert result["version"] == 1


class TestClearCache:
    """Tests for clear_cache function."""

    def test_clears_memory_cache(self):
        """Test clears memory cache."""
        from backend.licensing import public_key

        # Set up cache
        public_key._cache["public_key"] = "cached-data"

        mock_file = MagicMock()
        mock_file.exists.return_value = False

        with patch.object(public_key, "CACHE_FILE", mock_file):
            public_key.clear_cache()

        assert public_key._cache["public_key"] is None

    def test_deletes_file_cache(self):
        """Test deletes file cache."""
        from backend.licensing import public_key

        mock_file = MagicMock()
        mock_file.exists.return_value = True

        with patch.object(public_key, "CACHE_FILE", mock_file):
            public_key.clear_cache()

        mock_file.unlink.assert_called_once()

    def test_handles_file_delete_error(self):
        """Test handles file deletion errors gracefully."""
        from backend.licensing import public_key

        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_file.unlink.side_effect = Exception("Permission denied")

        with patch.object(public_key, "CACHE_FILE", mock_file):
            # Should not raise
            public_key.clear_cache()

        assert public_key._cache["public_key"] is None


class TestModuleConstants:
    """Tests for module constants."""

    def test_key_algorithm_constant(self):
        """Test KEY_ALGORITHM constant."""
        from backend.licensing.public_key import KEY_ALGORITHM

        assert KEY_ALGORITHM == "ES512"

    def test_key_curve_constant(self):
        """Test KEY_CURVE constant."""
        from backend.licensing.public_key import KEY_CURVE

        assert KEY_CURVE == "P-521"

    def test_key_version_constant(self):
        """Test KEY_VERSION constant."""
        from backend.licensing.public_key import KEY_VERSION

        assert KEY_VERSION == 1

    def test_cache_dir_is_path(self):
        """Test CACHE_DIR is a Path object."""
        from backend.licensing.public_key import CACHE_DIR

        assert isinstance(CACHE_DIR, Path)

    def test_cache_file_is_path(self):
        """Test CACHE_FILE is a Path object."""
        from backend.licensing.public_key import CACHE_FILE

        assert isinstance(CACHE_FILE, Path)
