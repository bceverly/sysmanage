# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.4: customer servers do not call the license server in step.

Fixed first delays (5 / 30 minutes) and fixed intervals kept servers that
restarted together calling in the same minute forever; startup blocked on the
license server and fetched the public key before looking at its cache.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.licensing import license_service as ls


class _Stop(BaseException):
    pass


async def _sleeps(coro_factory, count=4):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= count:
            raise _Stop()

    with patch.object(ls.asyncio, "sleep", fake_sleep):
        with pytest.raises(_Stop):
            await coro_factory()
    return sleeps


async def test_phone_home_starts_at_a_random_moment_and_jitters():
    service = ls.LicenseService()
    service._cached_license = MagicMock()  # the loop runs while one is loaded
    firsts, intervals = set(), []
    with patch.object(
        service, "_get_phone_home_interval", return_value=24
    ), patch.object(service, "_check_license_term", return_value=True), patch.object(
        service, "_phone_home", AsyncMock(return_value=True)
    ):
        for _ in range(10):
            sleeps = await _sleeps(service._phone_home_loop)
            firsts.add(round(sleeps[0]))
            intervals += sleeps[1:]
    assert len(firsts) > 7 and all(300 <= f <= 1800 for f in firsts)
    assert all(0.75 * 86400 <= i <= 1.25 * 86400 for i in intervals)
    assert len({round(i) for i in intervals}) > 20


async def test_the_license_server_can_direct_the_next_check():
    service = ls.LicenseService()
    service._cached_license = MagicMock()

    async def phone_home():
        service._next_check_after = ls._server_hint(7200)
        return True

    with patch.object(
        service, "_get_phone_home_interval", return_value=24
    ), patch.object(service, "_check_license_term", return_value=True), patch.object(
        service, "_phone_home", phone_home
    ):
        sleeps = await _sleeps(service._phone_home_loop, count=3)
    assert sleeps[1:] == [7200.0, 7200.0]


def test_server_hints_are_bounded():
    assert ls._server_hint(1) == ls._MIN_HINT_SECONDS
    assert ls._server_hint(10**9) == ls._MAX_HINT_SECONDS
    assert ls._server_hint("junk") is None and ls._server_hint(None) is None


async def test_a_background_startup_update_comes_within_minutes():
    service = ls.LicenseService()
    with patch.object(
        service, "_get_module_update_interval", return_value=6
    ), patch.object(ls.module_loader, "check_and_update_on_startup", AsyncMock()):
        soon = await _sleeps(lambda: service._module_update_loop(check_soon=True), 2)
        later = await _sleeps(lambda: service._module_update_loop(check_soon=False), 2)
    assert 60 <= soon[0] <= 300 and 1800 <= later[0] <= 3600
    assert 0.75 * 6 * 3600 <= soon[1] <= 1.25 * 6 * 3600


async def test_a_rotated_key_is_picked_up():
    with patch.object(
        ls, "get_public_key_pem", AsyncMock(return_value="old")
    ), patch.object(
        ls, "fetch_public_key", AsyncMock(return_value="new")
    ), patch.object(
        ls,
        "validate_license",
        side_effect=lambda _k, key: MagicMock(valid=key == "new"),
    ):
        result = await ls.LicenseService._validate_with_key("lic")
    assert result.valid


async def test_a_valid_cached_key_needs_no_fetch():
    fetch = AsyncMock(return_value="new")
    with patch.object(
        ls, "get_public_key_pem", AsyncMock(return_value="old")
    ), patch.object(ls, "fetch_public_key", fetch), patch.object(
        ls, "validate_license", return_value=MagicMock(valid=True)
    ):
        await ls.LicenseService._validate_with_key("lic")
    fetch.assert_not_called()


def test_asyncio_is_the_module_used_for_waits():
    assert ls.asyncio is asyncio


async def test_an_engine_without_a_plugin_bundle_is_not_asked_again(tmp_path):
    from backend.licensing import (
        plugin_bundle_loader as pbl,
    )  # pylint: disable=import-outside-toplevel

    loader = pbl.PluginBundleLoader()
    calls = []

    async def refused(_url, _key, _temp):
        calls.append(1)
        loader.last_fetch_status = 404
        return None

    with patch.object(
        loader, "_get_plugin_download_url", return_value="https://lic"
    ), patch(
        "backend.licensing.plugin_bundle_loader.get_config",
        return_value={"license": {"key": "k", "modules_path": str(tmp_path)}},
    ), patch.object(
        loader, "_get_modules_path", return_value=str(tmp_path)
    ), patch.object(
        loader, "_fetch_bundle_to_temp", refused
    ):
        assert await loader._download_plugin_bundle("health_engine") is False
        assert await loader._download_plugin_bundle("health_engine") is False
    assert len(calls) == 1


class _Resp:
    def __init__(self, status, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self.content = self

    async def iter_chunked(self, _n):
        yield self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(
        self, url, headers=None, timeout=None, allow_redirects=True
    ):  # noqa: ARG002
        self.requests.append((url, dict(headers or {})))
        return self.responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


async def _fetch(session, tmp_path):
    from backend.licensing.module_loader import (
        ModuleLoader,
    )  # pylint: disable=import-outside-toplevel

    loader = ModuleLoader()
    with patch(
        "backend.licensing.module_loader.aiohttp.ClientSession", return_value=session
    ):
        return await loader._fetch_module_bytes(
            "https://lic/download/x", "LICENSE-KEY", str(tmp_path / "x.tmp"), "x", {}
        )


async def test_a_redirect_to_storage_is_followed_without_the_license_key(tmp_path):
    session = _Session([
        _Resp(307, {"Location": "https://acct.r2.example/b/k?sig=1",
                    "X-Content-SHA512": "abc", "X-Module-Version": "2.1.0"}),
        _Resp(200, body=b"bundle-bytes"),
    ])  # fmt: skip
    assert await _fetch(session, tmp_path) == ("abc", "2.1.0")
    assert (tmp_path / "x.tmp").read_bytes() == b"bundle-bytes"
    assert session.requests[1][0].startswith("https://acct.r2.example/")
    assert "X-License-Key" not in session.requests[1][1]


async def test_a_refused_storage_link_falls_back_to_the_license_server(tmp_path):
    """2026-10-06: the license server's storage credential had no access and
    R2 answered 403 for every engine -- no customer could update.  The
    client now asks the license server to send the bytes itself."""
    session = _Session([
        _Resp(307, {"Location": "https://acct.r2.example/b/k?sig=1",
                    "X-Content-SHA512": "abc", "X-Module-Version": "2.1.0"}),
        _Resp(403),
        _Resp(200, {"X-Content-SHA512": "abc", "X-Module-Version": "2.1.0"}, b"direct"),
    ])  # fmt: skip
    assert await _fetch(session, tmp_path) == ("abc", "2.1.0")
    assert (tmp_path / "x.tmp").read_bytes() == b"direct"
    url, headers = session.requests[2]
    assert url == "https://lic/download/x"
    assert headers == {"X-License-Key": "LICENSE-KEY", "X-Module-Direct": "1"}


async def test_an_older_license_server_that_redirects_again_fails_cleanly(tmp_path):
    session = _Session([
        _Resp(307, {"Location": "https://acct.r2.example/b/k?sig=1"}),
        _Resp(403),
        _Resp(307, {"Location": "https://acct.r2.example/b/k?sig=2"}),
    ])  # fmt: skip
    assert await _fetch(session, tmp_path) is None
    assert len(session.requests) == 3


async def test_a_non_https_redirect_is_refused(tmp_path):
    session = _Session([_Resp(302, {"Location": "http://evil.example/x"})])
    assert await _fetch(session, tmp_path) is None
    assert len(session.requests) == 1


async def test_a_direct_download_still_works(tmp_path):
    session = _Session([_Resp(200, {"X-Content-SHA512": "h", "X-Module-Version": "1.0"},
                              b"direct")])  # fmt: skip
    assert await _fetch(session, tmp_path) == ("h", "1.0")
    assert (tmp_path / "x.tmp").read_bytes() == b"direct"


async def test_one_versions_call_per_update_cycle():
    from backend.licensing.module_loader import (
        ModuleLoader,
    )  # pylint: disable=import-outside-toplevel

    loader = ModuleLoader()
    versions = AsyncMock(return_value={"modules": {}, "plugins": {}})
    with patch.object(loader, "query_server_versions", versions), patch.object(
        loader._plugin_loader, "update_plugins", AsyncMock(return_value={})
    ):
        await loader.update_modules()
    assert versions.await_count == 1


def test_the_public_key_cache_location_is_configurable(tmp_path):
    """A second server on one machine (the load-test stack) must not share --
    or overwrite -- the installed server's key."""
    from backend.licensing import public_key  # pylint: disable=import-outside-toplevel

    target = tmp_path / "keys" / "public_key.pem"
    with patch.object(public_key, "get_config",return_value={"license": {"public_key_path": str(target)}}):  # fmt: skip
        assert public_key._cache_file() == target
    with patch.object(public_key, "get_config", return_value={"license": {}}):
        assert public_key._cache_file() == public_key.CACHE_FILE
