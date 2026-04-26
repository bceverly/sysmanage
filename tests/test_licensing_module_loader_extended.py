"""
Extended tests for backend.licensing.module_loader.

The original test file (test_licensing_module_loader.py) covers the easy
surface (properties, constants, simple branches). This file targets the
substantial uncovered branches: the DB-backed cache helpers, the aiohttp
download path with hash verification, the multi-stage update_modules
orchestration, and the startup hook.

Strategy: we mock the SQLAlchemy session via ``sessionmaker`` (matching the
pattern already used in the original file) and stub the aiohttp client at
the ``ClientSession`` boundary so we exercise the orchestration code without
booting a real HTTP stack.
"""

import os
import tempfile
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@contextmanager
def _patch_session(rows=None, raise_on_query=None):
    """Patch sessionmaker so the loader sees a controllable session.

    rows: either a single MagicMock (the .first() result) or a list of mocks
    (the .all() result). Pass None for an empty result.
    raise_on_query: if set, .query() raises this exception (for error paths).
    """
    mock_session = MagicMock()
    if raise_on_query is not None:
        mock_session.query.side_effect = raise_on_query
    else:
        first_value = (
            rows if not isinstance(rows, list) else (rows[0] if rows else None)
        )
        all_value = rows if isinstance(rows, list) else ([] if rows is None else [rows])

        # The loader chains queries in several shapes:
        #   query().filter().first()
        #   query().filter().filter().first()         (when version is supplied)
        #   query().filter().order_by().first()       (when version is not supplied)
        #   query().filter().all()                    (remove_cached_module)
        # Walking back from .first() / .all() / .order_by() to make every shape
        # resolve to the same first/all values is simpler than enumerating chains.
        def _wire(node):
            node.first.return_value = first_value
            node.all.return_value = all_value
            node.order_by.return_value.first.return_value = first_value
            node.order_by.return_value.all.return_value = all_value

        chain1 = mock_session.query.return_value.filter.return_value
        chain2 = chain1.filter.return_value
        _wire(chain1)
        _wire(chain2)

    with patch(
        "backend.licensing.module_loader.sessionmaker"
    ) as mock_sessionmaker, patch(
        "backend.licensing.module_loader.db_module.get_engine"
    ):
        cm = mock_sessionmaker.return_value.return_value
        cm.__enter__ = MagicMock(return_value=mock_session)
        cm.__exit__ = MagicMock(return_value=None)
        yield mock_session


def _config_with(license_extras=None):
    """Build a config dict with sensible license defaults."""
    base = {
        "phone_home_url": "https://license.example.com",
        "key": "test-license-key",
        "modules_path": "/tmp/sm-modules-test",
    }
    if license_extras:
        base.update(license_extras)
    return {"license": base}


# ---------------------------------------------------------------------------
# _get_cached_module_path
# ---------------------------------------------------------------------------


class TestGetCachedModulePath:
    def test_returns_file_path_when_entry_found_with_explicit_version(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        entry = MagicMock(file_path="/cache/health.so")

        with _patch_session(rows=entry) as session:
            result = loader._get_cached_module_path("health_engine", version="1.2.3")
        assert result == "/cache/health.so"
        # When version is supplied, the loader filters by it (no ordering).
        assert session.query.return_value.filter.return_value.filter.called

    def test_returns_latest_when_no_version_specified(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        entry = MagicMock(file_path="/cache/latest.so")

        with _patch_session(rows=entry):
            result = loader._get_cached_module_path("health_engine")
        assert result == "/cache/latest.so"

    def test_returns_none_when_no_entry(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(rows=None):
            assert loader._get_cached_module_path("missing_module") is None

    def test_db_error_returns_none(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(raise_on_query=RuntimeError("db down")):
            assert loader._get_cached_module_path("health_engine") is None


# ---------------------------------------------------------------------------
# ensure_module_available — non-proplus_core paths
# ---------------------------------------------------------------------------


class TestEnsureModuleAvailable:
    @pytest.mark.asyncio
    async def test_uses_cached_path_when_present(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True

        cache_file = tmp_path / "engine.so"
        cache_file.write_bytes(b"x")

        with patch.object(
            loader, "_get_cached_module_path", return_value=str(cache_file)
        ), patch.object(
            loader, "_load_module_from_path", return_value=True
        ) as load, patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=True)
        ):
            ok = await loader.ensure_module_available("health_engine")
        assert ok is True
        load.assert_called_once_with("health_engine", str(cache_file))

    @pytest.mark.asyncio
    async def test_downloads_when_cache_misses(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True

        with patch.object(
            loader, "_get_cached_module_path", return_value=None
        ), patch.object(
            loader, "_download_and_cache_module", new=AsyncMock(return_value=True)
        ) as download, patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=True)
        ):
            ok = await loader.ensure_module_available("health_engine", version="1.0")
        assert ok is True
        download.assert_awaited_once_with("health_engine", "1.0")

    @pytest.mark.asyncio
    async def test_calls_initialize_when_not_initialised(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = False

        with patch.object(loader, "initialize") as init, patch.object(
            loader, "_get_cached_module_path", return_value=None
        ), patch.object(
            loader, "_download_and_cache_module", new=AsyncMock(return_value=False)
        ), patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=False)
        ):
            await loader.ensure_module_available("health_engine")
        init.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_loaded_skips_cache_check(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        loader._initialized = True
        loader._loaded_modules["health_engine"] = MagicMock()

        with patch.object(loader, "_get_cached_module_path") as get_cache, patch.object(
            loader, "_download_and_cache_module"
        ) as download, patch.object(
            loader, "ensure_plugin_available", new=AsyncMock(return_value=True)
        ):
            ok = await loader.ensure_module_available("health_engine")
        assert ok is True
        # Already loaded → no cache lookup, no download.
        get_cache.assert_not_called()
        download.assert_not_called()


# ---------------------------------------------------------------------------
# _save_module_to_cache
# ---------------------------------------------------------------------------


class TestSaveModuleToCache:
    def test_inserts_new_row_when_no_existing(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(rows=None) as session:
            loader._save_module_to_cache(
                module_code="health_engine",
                version="1.0.0",
                platform_info={
                    "platform": "linux",
                    "architecture": "x86_64",
                    "python_version": "3.12",
                },
                file_path="/path/to/file.so",
                file_hash="abc",
            )
        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_updates_existing_row(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        existing = MagicMock()
        with _patch_session(rows=existing) as session:
            loader._save_module_to_cache(
                module_code="health_engine",
                version="1.0.0",
                platform_info={
                    "platform": "linux",
                    "architecture": "x86_64",
                    "python_version": "3.12",
                },
                file_path="/path/to/new.so",
                file_hash="def",
            )
        # Updated existing row, did not add a new one.
        session.add.assert_not_called()
        assert existing.file_path == "/path/to/new.so"
        assert existing.file_hash == "def"
        session.commit.assert_called_once()

    def test_db_error_rolls_back(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(raise_on_query=RuntimeError("db down")) as session:
            # Should not raise — errors are logged.
            loader._save_module_to_cache(
                module_code="x",
                version="1",
                platform_info={
                    "platform": "linux",
                    "architecture": "x86_64",
                    "python_version": "3.12",
                },
                file_path="/p",
                file_hash="h",
            )
        session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# _download_and_cache_module
# ---------------------------------------------------------------------------


class _FakeAioResponse:
    """Minimal aiohttp.ClientResponse stand-in supporting the API the loader uses."""

    def __init__(self, status=200, headers=None, chunks=(b"data",)):
        self.status = status
        self.headers = headers or {}
        self._chunks = chunks
        self.content = self  # iter_chunked is on .content; loader does response.content.iter_chunked

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def iter_chunked(self, _size):
        for c in self._chunks:
            yield c


class _FakeAioSession:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None, timeout=None):
        # aiohttp's session.get is a context manager too.
        return self._response


class TestDownloadAndCacheModule:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_download_url(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value={"license": {}},
        ):
            assert await loader._download_and_cache_module("any") is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_license_key(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        # Has phone_home_url so download URL resolves, but no key.
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value={"license": {"phone_home_url": "https://l.example/"}},
        ):
            assert await loader._download_and_cache_module("any") is False

    @pytest.mark.asyncio
    async def test_returns_false_on_non_200_response(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        modules_path = tmp_path / "mods"
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with({"modules_path": str(modules_path)}),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_FakeAioSession(_FakeAioResponse(status=500)),
        ):
            assert await loader._download_and_cache_module("m") is False

    @pytest.mark.asyncio
    async def test_hash_mismatch_aborts_and_cleans_up(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        modules_path = tmp_path / "mods"
        # Configure server to return hash that won't match the actual file content.
        bogus_hash = "deadbeef" * 16  # length matches sha512 hex
        response = _FakeAioResponse(
            status=200,
            headers={"X-Content-SHA512": bogus_hash, "X-Module-Version": "9.9.9"},
            chunks=(b"hello world",),
        )
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with({"modules_path": str(modules_path)}),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_FakeAioSession(response),
        ):
            result = await loader._download_and_cache_module("m")
        assert result is False
        # Temp file should have been removed on hash mismatch.
        assert not (modules_path / "m.tmp").exists()

    @pytest.mark.asyncio
    async def test_happy_path_downloads_loads_and_caches(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        modules_path = tmp_path / "mods"
        # No expected hash → loader skips verification.
        response = _FakeAioResponse(
            status=200,
            headers={"X-Module-Version": "1.2.3"},
            chunks=(b"so-bytes",),
        )
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with({"modules_path": str(modules_path)}),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_FakeAioSession(response),
        ), patch.object(
            loader, "_save_module_to_cache"
        ) as save_cache, patch.object(
            loader, "_load_module_from_path", return_value=True
        ) as load_module:
            result = await loader._download_and_cache_module("m")
        assert result is True
        save_cache.assert_called_once()
        load_module.assert_called_once()
        # .so file should exist at the final path.
        kwargs = save_cache.call_args.kwargs
        assert os.path.exists(kwargs["file_path"])
        assert kwargs["version"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_network_error_returns_false_and_cleans_temp(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader
        import aiohttp

        loader = ModuleLoader()
        modules_path = tmp_path / "mods"
        modules_path.mkdir()
        # Pre-create a temp file so we can verify the cleanup path runs.
        temp_file = modules_path / "m.tmp"
        temp_file.write_bytes(b"partial")

        class _BoomSession:
            async def __aenter__(self):
                raise aiohttp.ClientError("network exploded")

            async def __aexit__(self, *a):
                return False

        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with({"modules_path": str(modules_path)}),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_BoomSession(),
        ):
            assert await loader._download_and_cache_module("m") is False
        assert not temp_file.exists()


# ---------------------------------------------------------------------------
# _load_module_from_path success path
# ---------------------------------------------------------------------------


class TestLoadModuleFromPathSuccess:
    def test_load_module_from_path_records_in_loaded_modules(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        # Synthesise a tiny .py file as a stand-in for a Cython .so.
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("VALUE = 42\n")
            module_path = f.name
        try:
            ok = loader._load_module_from_path("synthetic_engine", module_path)
            assert ok is True
            assert "synthetic_engine" in loader._loaded_modules
            assert loader.get_module("synthetic_engine").VALUE == 42
        finally:
            os.unlink(module_path)
            # Clean up sys.modules so other tests aren't affected.
            import sys

            sys.modules.pop("synthetic_engine", None)


# ---------------------------------------------------------------------------
# _get_cached_module_version / _hash — additional branches
# ---------------------------------------------------------------------------


class TestGetCachedModuleHashFound:
    def test_returns_hash_when_present(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        entry = MagicMock(file_hash="cafef00d")
        with _patch_session(rows=entry):
            assert loader._get_cached_module_hash("m") == "cafef00d"

    def test_returns_none_when_missing(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(rows=None):
            assert loader._get_cached_module_hash("m") is None


# ---------------------------------------------------------------------------
# query_server_versions — happy path and error branches
# ---------------------------------------------------------------------------


class _AioJsonResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._payload


class _AioGetSession:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None, timeout=None):
        return self._response


class TestQueryServerVersions:
    @pytest.mark.asyncio
    async def test_returns_modules_and_plugins_payload(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        payload = {
            "modules": [
                {"code": "av", "latest_version": "1.2", "file_hash": "h1"},
                {"code": "fw", "latest_version": "2.0", "file_hash": "h2"},
            ],
            "plugins": [
                {"code": "av", "latest_version": "1.2", "file_hash": "p1"},
            ],
        }
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with(),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_AioGetSession(_AioJsonResponse(200, payload)),
        ):
            out = await loader.query_server_versions()
        assert out["modules"]["av"] == {"version": "1.2", "file_hash": "h1"}
        assert out["plugins"]["av"]["version"] == "1.2"

    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with(),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_AioGetSession(_AioJsonResponse(503, {})),
        ):
            assert await loader.query_server_versions() == {}

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        from backend.licensing.module_loader import ModuleLoader
        import aiohttp

        loader = ModuleLoader()

        class _Boom:
            async def __aenter__(self):
                raise aiohttp.ClientError("nope")

            async def __aexit__(self, *a):
                return False

        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with(),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_Boom(),
        ):
            assert await loader.query_server_versions() == {}

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_empty(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        class _Crash:
            async def __aenter__(self):
                raise RuntimeError("bug")

            async def __aexit__(self, *a):
                return False

        with patch(
            "backend.licensing.module_loader.get_config",
            return_value=_config_with(),
        ), patch(
            "backend.licensing.module_loader.aiohttp.ClientSession",
            return_value=_Crash(),
        ):
            assert await loader.query_server_versions() == {}


# ---------------------------------------------------------------------------
# check_for_updates — version match, hash mismatch, up-to-date
# ---------------------------------------------------------------------------


class TestCheckForUpdatesAdvanced:
    @pytest.mark.asyncio
    async def test_version_match_and_hash_match_no_update(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(
                return_value={
                    "modules": {
                        "m": {"version": "1.0", "file_hash": "abc"},
                    }
                }
            ),
        ), patch.object(
            loader, "_get_cached_module_version", return_value="1.0"
        ), patch.object(
            loader, "_get_cached_module_hash", return_value="abc"
        ):
            assert await loader.check_for_updates() == []

    @pytest.mark.asyncio
    async def test_version_match_but_hash_mismatch_triggers_update(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(
                return_value={
                    "modules": {
                        "m": {"version": "1.0", "file_hash": "abc"},
                    }
                }
            ),
        ), patch.object(
            loader, "_get_cached_module_version", return_value="1.0"
        ), patch.object(
            loader, "_get_cached_module_hash", return_value="zzz"
        ):
            assert await loader.check_for_updates() == ["m"]

    @pytest.mark.asyncio
    async def test_version_mismatch_triggers_update(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(
                return_value={"modules": {"m": {"version": "2.0", "file_hash": "h"}}}
            ),
        ), patch.object(loader, "_get_cached_module_version", return_value="1.0"):
            assert await loader.check_for_updates() == ["m"]

    @pytest.mark.asyncio
    async def test_old_format_dict_passes_through(self):
        """If query_server_versions ever regresses to the flat dict shape, the
        loader still treats it as the modules block."""
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(
                return_value={"old_module": {"version": "1.0", "file_hash": ""}}
            ),
        ), patch.object(loader, "_get_cached_module_version", return_value=None):
            # The loader pulls server_data.get("modules", server_data) — when
            # there is no "modules" key, it treats the whole dict as the
            # versions table.
            updates = await loader.check_for_updates()
        assert "old_module" in updates


# ---------------------------------------------------------------------------
# update_modules orchestration
# ---------------------------------------------------------------------------


class TestUpdateModules:
    @pytest.mark.asyncio
    async def test_no_updates_returns_only_plugin_results(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader, "check_for_updates", new=AsyncMock(return_value=[])
        ), patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value={})
        ), patch.object(
            loader._plugin_loader,
            "update_plugins",
            new=AsyncMock(return_value={"p1": True}),
        ):
            results = await loader.update_modules()
        assert results == {"p1_plugin": True}

    @pytest.mark.asyncio
    async def test_updates_two_modules_in_parallel(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader, "check_for_updates", new=AsyncMock(return_value=["a", "b"])
        ), patch.object(loader, "unload_module", return_value=True), patch.object(
            loader, "_remove_cached_module"
        ), patch.object(
            loader, "_download_and_cache_module", new=AsyncMock(return_value=True)
        ), patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value={})
        ), patch.object(
            loader._plugin_loader,
            "update_plugins",
            new=AsyncMock(return_value={}),
        ):
            results = await loader.update_modules()
        assert results == {"a": True, "b": True}

    @pytest.mark.asyncio
    async def test_failure_with_cached_fallback_reloads_old_version(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        old_path = tmp_path / "old.so"
        old_path.write_bytes(b"old")

        with patch.object(
            loader, "check_for_updates", new=AsyncMock(return_value=["a"])
        ), patch.object(loader, "unload_module", return_value=True), patch.object(
            loader, "_remove_cached_module"
        ), patch.object(
            loader,
            "_download_and_cache_module",
            new=AsyncMock(return_value=False),
        ), patch.object(
            loader, "_get_cached_module_path", return_value=str(old_path)
        ), patch.object(
            loader, "_load_module_from_path", return_value=True
        ) as reload, patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value={})
        ), patch.object(
            loader._plugin_loader,
            "update_plugins",
            new=AsyncMock(return_value={}),
        ):
            results = await loader.update_modules()
        assert results == {"a": False}
        reload.assert_called_once_with("a", str(old_path))

    @pytest.mark.asyncio
    async def test_download_exception_does_not_break_other_modules(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()

        async def _download(mc):
            if mc == "a":
                raise RuntimeError("explode")
            return True

        with patch.object(
            loader, "check_for_updates", new=AsyncMock(return_value=["a", "b"])
        ), patch.object(loader, "unload_module", return_value=False), patch.object(
            loader, "_remove_cached_module"
        ), patch.object(
            loader, "_download_and_cache_module", new=AsyncMock(side_effect=_download)
        ), patch.object(
            loader, "query_server_versions", new=AsyncMock(return_value={})
        ), patch.object(
            loader._plugin_loader,
            "update_plugins",
            new=AsyncMock(return_value={}),
        ):
            results = await loader.update_modules()
        # 'a' raised → not in results; 'b' succeeded.
        assert "a" not in results
        assert results.get("b") is True


# ---------------------------------------------------------------------------
# _remove_cached_module
# ---------------------------------------------------------------------------


class TestRemoveCachedModule:
    def test_removes_files_and_db_records(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        f1 = tmp_path / "a.so"
        f1.write_bytes(b"x")
        e1 = MagicMock(file_path=str(f1))
        e2 = MagicMock(file_path="/non/existent.so")  # nonexistent path branch

        with _patch_session(rows=[e1, e2]) as session:
            loader._remove_cached_module("m")

        assert not f1.exists()
        assert session.delete.call_count == 2
        session.commit.assert_called_once()

    def test_handles_os_remove_failure(self, tmp_path):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        f1 = tmp_path / "b.so"
        f1.write_bytes(b"x")
        entry = MagicMock(file_path=str(f1))

        with _patch_session(rows=[entry]) as session, patch(
            "backend.licensing.module_loader.os.remove",
            side_effect=OSError("perm denied"),
        ):
            # Should not raise — just logs the warning.
            loader._remove_cached_module("m")
        session.delete.assert_called_once_with(entry)
        session.commit.assert_called_once()

    def test_db_error_rolls_back(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with _patch_session(raise_on_query=RuntimeError("db down")) as session:
            loader._remove_cached_module("m")
        session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Plugin delegation methods
# ---------------------------------------------------------------------------


class TestPluginDelegation:
    @pytest.mark.asyncio
    async def test_check_for_plugin_updates_passes_server_versions(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(return_value={"modules": {}, "plugins": {}}),
        ), patch.object(
            loader._plugin_loader,
            "check_for_plugin_updates",
            return_value=["av"],
        ) as check:
            assert await loader.check_for_plugin_updates() == ["av"]
        check.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_plugins_delegates(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "query_server_versions",
            new=AsyncMock(return_value={}),
        ), patch.object(
            loader._plugin_loader,
            "update_plugins",
            new=AsyncMock(return_value={"av": True}),
        ):
            assert await loader.update_plugins() == {"av": True}


# ---------------------------------------------------------------------------
# check_and_update_on_startup
# ---------------------------------------------------------------------------


class TestCheckAndUpdateOnStartup:
    @pytest.mark.asyncio
    async def test_logs_no_updates_when_results_empty(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(loader, "update_modules", new=AsyncMock(return_value={})):
            # Should run without raising.
            await loader.check_and_update_on_startup()

    @pytest.mark.asyncio
    async def test_logs_updated_and_failed(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader,
            "update_modules",
            new=AsyncMock(return_value={"a": True, "b": False}),
        ):
            await loader.check_and_update_on_startup()  # smoke

    @pytest.mark.asyncio
    async def test_swallow_exception_from_update_modules(self):
        from backend.licensing.module_loader import ModuleLoader

        loader = ModuleLoader()
        with patch.object(
            loader, "update_modules", new=AsyncMock(side_effect=RuntimeError("x"))
        ):
            # Must not propagate — startup hook is best-effort.
            await loader.check_and_update_on_startup()
