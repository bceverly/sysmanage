# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Tests for ``backend/services/geolocation_service.py`` (Phase 12.7).

Covers:
  * Internal-IP detection (private, loopback, link-local, CGNAT, etc.)
  * lookup_ip happy paths via GeoLite2 + ipapi.co
  * Short-circuit behavior when geo_lookup is disabled / for internal IPs
  * Tarball extraction safety in refresh_geolite_db (path-traversal reject)
  * Background refresh task self-skips when no MaxMind key is configured

GeoLite2 reads + ipapi.co network are mocked — these tests don't touch
either external dependency.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import io
import os
import tarfile

from unittest.mock import MagicMock, patch

import pytest

from backend.services import geolocation_service as geo

# ---------------------------------------------------------------------
# is_internal_ip
# ---------------------------------------------------------------------


class TestIsInternalIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "10.0.0.1",  # RFC 1918
            "172.16.0.5",  # RFC 1918
            "192.168.1.50",  # RFC 1918
            "100.64.0.1",  # RFC 6598 (CGNAT) — the one Python's stdlib misses
            "127.0.0.1",  # loopback
            "169.254.1.1",  # IPv4 link-local
            "::1",  # IPv6 loopback
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 ULA
            "224.0.0.1",  # multicast
            "0.0.0.0",  # unspecified
            "",  # empty
            "not-an-ip",  # malformed (treated as internal -> skip)
        ],
    )
    def test_internal_ips_return_true(self, ip):
        assert geo.is_internal_ip(ip) is True

    @pytest.mark.parametrize(
        "ip",
        [
            "8.8.8.8",  # Google DNS
            "1.1.1.1",  # Cloudflare DNS
            "199.83.131.1",  # arbitrary public IPv4
            "2606:4700:4700::1111",  # Cloudflare IPv6
        ],
    )
    def test_public_ips_return_false(self, ip):
        assert geo.is_internal_ip(ip) is False


# ---------------------------------------------------------------------
# lookup_ip — short-circuit paths
# ---------------------------------------------------------------------


class TestLookupIpShortCircuit:
    def test_returns_none_when_disabled(self):
        with patch.object(geo, "is_geo_lookup_enabled", return_value=False):
            assert geo.lookup_ip("8.8.8.8") is None

    def test_returns_none_for_internal_ip(self):
        # Even with geo_lookup enabled, internal IPs short-circuit.
        with patch.object(geo, "is_geo_lookup_enabled", return_value=True):
            assert geo.lookup_ip("10.0.0.1") is None

    def test_returns_none_for_empty_string(self):
        with patch.object(geo, "is_geo_lookup_enabled", return_value=True):
            assert geo.lookup_ip("") is None

    def test_returns_none_for_non_string(self):
        with patch.object(geo, "is_geo_lookup_enabled", return_value=True):
            # The signature is typed str but defensive against bad
            # callers; verify we don't crash on None / int.
            assert geo.lookup_ip(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# lookup_ip — GeoLite2 path
# ---------------------------------------------------------------------


def _stub_geolite_response(country="US", subdivision="CA", city="San Francisco"):
    """Build a fake response object mimicking geoip2.models.City."""
    response = MagicMock()
    response.country.iso_code = country
    if subdivision:
        sub = MagicMock()
        sub.iso_code = subdivision
        response.subdivisions = MagicMock()
        response.subdivisions.most_specific = sub
    else:
        response.subdivisions = MagicMock()
        response.subdivisions.most_specific.iso_code = None
    response.city.name = city
    response.location.latitude = 37.7749
    response.location.longitude = -122.4194
    return response


class TestLookupIpGeoLite2:
    def test_geolite_hit_returns_geo_result(self):
        fake_reader = MagicMock()
        fake_reader.city.return_value = _stub_geolite_response()
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(geo._reader_holder, "get_reader", return_value=fake_reader):
            result = geo.lookup_ip("8.8.8.8")
        assert result is not None
        assert result.country_code == "US"
        assert result.subdivision_code == "US-CA"
        assert result.city == "San Francisco"
        assert result.latitude == pytest.approx(37.7749)
        assert result.longitude == pytest.approx(-122.4194)
        assert result.source == "geolite2"

    def test_geolite_response_without_country_falls_through(self):
        """A response with no ``country.iso_code`` should fall through
        to the ipapi.co fallback rather than return a half-populated
        GeoResult."""
        fake_reader = MagicMock()
        fake_reader.city.return_value = _stub_geolite_response(country="")
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=fake_reader
        ), patch.object(
            geo, "_lookup_via_ipapi", return_value=None
        ) as ipapi_mock:
            result = geo.lookup_ip("8.8.8.8")
        assert result is None
        ipapi_mock.assert_called_once()

    def test_no_reader_falls_through_to_ipapi(self):
        """When the bundled DB isn't open, lookups should fall to
        ipapi.co rather than crash."""
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=None
        ), patch.object(
            geo, "_lookup_via_ipapi", return_value=None
        ) as ipapi_mock:
            result = geo.lookup_ip("8.8.8.8")
        assert result is None
        ipapi_mock.assert_called_once_with("8.8.8.8")


# ---------------------------------------------------------------------
# lookup_ip — ipapi.co fallback path
# ---------------------------------------------------------------------


class TestLookupIpIpapi:
    def _patch_httpx_get(self, *, status_code=200, payload=None, raise_exc=None):
        response = MagicMock()
        response.status_code = status_code
        if raise_exc is None:
            response.json.return_value = payload or {}
        return (
            patch.object(geo.httpx, "get", side_effect=raise_exc or [response])
            if raise_exc
            else patch.object(geo.httpx, "get", return_value=response)
        )

    def test_ipapi_hit_returns_geo_result(self):
        payload = {
            "country_code": "DE",
            "region_code": "BY",
            "city": "Munich",
            "latitude": 48.1374,
            "longitude": 11.5755,
        }
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=None
        ), self._patch_httpx_get(
            payload=payload
        ):
            result = geo.lookup_ip("199.83.131.1")
        assert result is not None
        assert result.country_code == "DE"
        assert result.subdivision_code == "DE-BY"
        assert result.city == "Munich"
        assert result.latitude == pytest.approx(48.1374)
        assert result.longitude == pytest.approx(11.5755)
        assert result.source == "ipapi"

    def test_ipapi_rate_limit_payload_returns_none(self):
        """``ipapi.co`` returns ``{"error": true, ...}`` when the
        free-tier rate limit is exhausted.  Treat that as a miss
        rather than a partial GeoResult."""
        payload = {"error": True, "reason": "RateLimited"}
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=None
        ), self._patch_httpx_get(
            payload=payload
        ):
            result = geo.lookup_ip("199.83.131.1")
        assert result is None

    def test_ipapi_disabled_returns_none(self):
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=False
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=None
        ):
            result = geo.lookup_ip("199.83.131.1")
        assert result is None

    def test_ipapi_network_error_returns_none(self):
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(
            geo._reader_holder, "get_reader", return_value=None
        ), patch.object(
            geo.httpx,
            "get",
            side_effect=geo.httpx.RequestError("DNS failure"),
        ):
            result = geo.lookup_ip("199.83.131.1")
        assert result is None


# ---------------------------------------------------------------------
# refresh_geolite_db
# ---------------------------------------------------------------------


class TestRefreshGeoliteDb:
    def test_skips_when_no_license_key(self):
        with patch.object(geo, "get_geo_lookup_maxmind_license_key", return_value=""):
            assert geo.refresh_geolite_db() is False


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------


def test_no_geo_track_tag_constant_exists():
    """Heartbeat handler + host endpoint both import this name.  The
    string value is the operator-facing contract and shouldn't change
    without a migration of any existing host_tags rows."""
    assert geo.NO_GEO_TRACK_TAG == "no_geo_track"


# ---------------------------------------------------------------------
# _GeoLite2ReaderHolder
# ---------------------------------------------------------------------


class TestReaderHolder:
    def test_get_reader_returns_none_when_db_missing(self, tmp_path):
        holder = geo._GeoLite2ReaderHolder()
        missing = str(tmp_path / "does-not-exist.mmdb")
        with patch.object(geo, "get_geo_lookup_database_path", return_value=missing):
            assert holder.get_reader() is None

    def test_get_reader_open_failure_returns_none(self, tmp_path):
        # A file that exists but isn't a valid mmdb -> Reader() raises ->
        # holder swallows it and returns None (falls back to ipapi.co).
        bogus = tmp_path / "bogus.mmdb"
        bogus.write_bytes(b"not a real maxmind db")
        holder = geo._GeoLite2ReaderHolder()
        with patch.object(geo, "get_geo_lookup_database_path", return_value=str(bogus)):
            assert holder.get_reader() is None

    def test_get_reader_caches_and_reopens_on_path_change(self, tmp_path):
        holder = geo._GeoLite2ReaderHolder()
        fake_reader_a = MagicMock()
        fake_reader_b = MagicMock()
        path_a = str(tmp_path / "a.mmdb")
        path_b = str(tmp_path / "b.mmdb")
        (tmp_path / "a.mmdb").write_bytes(b"x")
        (tmp_path / "b.mmdb").write_bytes(b"x")

        import geoip2.database  # noqa: PLC0415

        made = iter([fake_reader_a, fake_reader_b])

        with patch.object(
            geoip2.database, "Reader", side_effect=lambda _p: next(made)
        ), patch.object(
            geo, "get_geo_lookup_database_path", side_effect=[path_a, path_a, path_b]
        ):
            r1 = holder.get_reader()
            r2 = holder.get_reader()  # cached, same path -> same object
            r3 = holder.get_reader()  # path changed -> reopen
        assert r1 is fake_reader_a
        assert r2 is fake_reader_a
        assert r3 is fake_reader_b
        # The old reader is closed on reopen.
        fake_reader_a.close.assert_called()

    def test_close_is_idempotent(self):
        holder = geo._GeoLite2ReaderHolder()
        holder.close()  # no reader -> no error
        holder._reader = MagicMock()
        holder._reader_path = "/x"
        holder.close()
        assert holder._reader is None
        assert holder._reader_path is None


# ---------------------------------------------------------------------
# _lookup_via_geolite2 — AddressNotFound + subdivision-less paths
# ---------------------------------------------------------------------


class TestLookupViaGeolite2:
    def test_address_not_found_returns_none(self):
        import geoip2.errors  # noqa: PLC0415

        reader = MagicMock()
        reader.city.side_effect = geoip2.errors.AddressNotFoundError("nope")
        with patch.object(geo._reader_holder, "get_reader", return_value=reader):
            assert geo._lookup_via_geolite2("8.8.8.8") is None

    def test_unexpected_error_returns_none(self):
        reader = MagicMock()
        reader.city.side_effect = RuntimeError("corrupt db")
        with patch.object(geo._reader_holder, "get_reader", return_value=reader):
            assert geo._lookup_via_geolite2("8.8.8.8") is None

    def test_no_subdivision_still_returns_result(self):
        reader = MagicMock()
        reader.city.return_value = _stub_geolite_response(subdivision=None)
        with patch.object(geo._reader_holder, "get_reader", return_value=reader):
            result = geo._lookup_via_geolite2("8.8.8.8")
        assert result is not None
        assert result.subdivision_code is None
        assert result.country_code == "US"


# ---------------------------------------------------------------------
# ipapi.co edge cases
# ---------------------------------------------------------------------


class TestIpapiEdges:
    def test_non_200_status_returns_none(self):
        response = MagicMock()
        response.status_code = 429
        with patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(geo.httpx, "get", return_value=response):
            assert geo._lookup_via_ipapi("8.8.8.8") is None

    def test_bad_json_returns_none(self):
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("bad json")
        with patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(geo.httpx, "get", return_value=response):
            assert geo._lookup_via_ipapi("8.8.8.8") is None

    def test_missing_country_code_returns_none(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"city": "Nowhere"}  # no country_code
        with patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(geo.httpx, "get", return_value=response):
            assert geo._lookup_via_ipapi("8.8.8.8") is None

    def test_no_region_yields_none_subdivision(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "country_code": "jp",  # lowercased on purpose
            "city": "Tokyo",
            "latitude": 35.6,
            "longitude": 139.7,
        }
        with patch.object(
            geo, "is_geo_lookup_ipapi_fallback_enabled", return_value=True
        ), patch.object(geo.httpx, "get", return_value=response):
            result = geo._lookup_via_ipapi("8.8.8.8")
        assert result is not None
        assert result.country_code == "JP"
        assert result.subdivision_code is None


# ---------------------------------------------------------------------
# refresh helpers: _locate_mmdb / _safe_extract_tarball / install
# ---------------------------------------------------------------------


def _tar_bytes(members: dict) -> bytes:
    """Build an in-memory tar.gz from ``{name: bytes}``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class TestRefreshHelpers:
    def test_locate_mmdb_finds_nested(self, tmp_path):
        nested = tmp_path / "GeoLite2-City_2026" / "GeoLite2-City.mmdb"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"db")
        assert geo._locate_mmdb(str(tmp_path)) == str(nested)

    def test_locate_mmdb_returns_none_when_absent(self, tmp_path):
        (tmp_path / "readme.txt").write_text("no db here")
        assert geo._locate_mmdb(str(tmp_path)) is None

    def test_safe_extract_accepts_normal_tarball(self, tmp_path):
        tar_path = tmp_path / "ok.tar.gz"
        tar_path.write_bytes(_tar_bytes({"dir/GeoLite2-City.mmdb": b"data"}))
        out = tmp_path / "out"
        out.mkdir()
        with tarfile.open(str(tar_path), "r:gz") as tar:
            assert geo._safe_extract_tarball(tar, str(out)) is True
        assert (out / "dir" / "GeoLite2-City.mmdb").is_file()

    def test_safe_extract_rejects_path_traversal(self, tmp_path):
        tar_path = tmp_path / "evil.tar.gz"
        tar_path.write_bytes(_tar_bytes({"../escape.mmdb": b"pwn"}))
        out = tmp_path / "out"
        out.mkdir()
        with tarfile.open(str(tar_path), "r:gz") as tar:
            assert geo._safe_extract_tarball(tar, str(out)) is False
        assert not (tmp_path / "escape.mmdb").exists()

    def test_safe_extract_rejects_decompression_bomb(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        # Fake a member whose declared size exceeds the cap without writing
        # gigabytes to disk.
        fake_member = MagicMock()
        fake_member.name = "big.mmdb"
        fake_member.size = geo._MAX_EXTRACT_BYTES + 1
        fake_tar = MagicMock()
        fake_tar.getmembers.return_value = [fake_member]
        assert geo._safe_extract_tarball(fake_tar, str(out)) is False
        fake_tar.extract.assert_not_called()

    def test_install_from_tarball_success(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db_path = str(db_dir / "GeoLite2-City.mmdb")
        tar_path = db_dir / "drop.tar.gz"
        tar_path.write_bytes(_tar_bytes({"nested/GeoLite2-City.mmdb": b"newdb"}))
        with patch.object(geo._reader_holder, "close"):
            ok = geo._install_mmdb_from_tarball(str(tar_path), str(db_dir), db_path)
        assert ok is True
        assert os.path.isfile(db_path)
        with open(db_path, "rb") as fh:
            assert fh.read() == b"newdb"

    def test_install_from_tarball_no_mmdb_returns_false(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db_path = str(db_dir / "GeoLite2-City.mmdb")
        tar_path = db_dir / "drop.tar.gz"
        tar_path.write_bytes(_tar_bytes({"README.txt": b"no db"}))
        assert (
            geo._install_mmdb_from_tarball(str(tar_path), str(db_dir), db_path) is False
        )

    def test_install_from_tarball_traversal_returns_false(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db_path = str(db_dir / "GeoLite2-City.mmdb")
        tar_path = db_dir / "evil.tar.gz"
        tar_path.write_bytes(_tar_bytes({"../evil.mmdb": b"x"}))
        assert (
            geo._install_mmdb_from_tarball(str(tar_path), str(db_dir), db_path) is False
        )

    def test_install_from_tarball_bad_archive_returns_false(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        db_path = str(db_dir / "GeoLite2-City.mmdb")
        bad = db_dir / "bad.tar.gz"
        bad.write_bytes(b"this is not a gzip tarball")
        assert geo._install_mmdb_from_tarball(str(bad), str(db_dir), db_path) is False


# ---------------------------------------------------------------------
# _download_maxmind_tarball
# ---------------------------------------------------------------------


class TestDownloadTarball:
    def _stream_ctx(self, *, status_code=200, chunks=(b"data",), raise_exc=None):
        response = MagicMock()
        response.status_code = status_code
        response.iter_bytes.return_value = list(chunks)
        cm = MagicMock()
        cm.__enter__.return_value = response
        cm.__exit__.return_value = False
        if raise_exc:
            return patch.object(geo.httpx, "stream", side_effect=raise_exc)
        return patch.object(geo.httpx, "stream", return_value=cm)

    def test_download_writes_tempfile(self, tmp_path):
        with self._stream_ctx(chunks=(b"abc", b"def")):
            path = geo._download_maxmind_tarball("http://x", str(tmp_path))
        assert path is not None
        with open(path, "rb") as fh:
            assert fh.read() == b"abcdef"

    def test_download_non_200_returns_none(self, tmp_path):
        with self._stream_ctx(status_code=401):
            assert geo._download_maxmind_tarball("http://x", str(tmp_path)) is None

    def test_download_network_error_returns_none(self, tmp_path):
        with self._stream_ctx(raise_exc=geo.httpx.RequestError("boom")):
            assert geo._download_maxmind_tarball("http://x", str(tmp_path)) is None


# ---------------------------------------------------------------------
# refresh_geolite_db — full orchestration
# ---------------------------------------------------------------------


class TestRefreshGeoliteDbFull:
    def test_success_path(self, tmp_path):
        db_path = str(tmp_path / "db" / "GeoLite2-City.mmdb")
        with patch.object(
            geo, "get_geo_lookup_maxmind_license_key", return_value="KEY"
        ), patch.object(
            geo, "get_geo_lookup_database_path", return_value=db_path
        ), patch.object(
            geo, "_download_maxmind_tarball", return_value=str(tmp_path / "t.tar.gz")
        ) as dl, patch.object(
            geo, "_install_mmdb_from_tarball", return_value=True
        ) as inst:
            # Create the tarball file so the finally-unlink succeeds.
            (tmp_path / "t.tar.gz").write_bytes(b"tar")
            assert geo.refresh_geolite_db() is True
        dl.assert_called_once()
        inst.assert_called_once()
        # The temp tarball is cleaned up.
        assert not (tmp_path / "t.tar.gz").exists()

    def test_download_failure_returns_false(self, tmp_path):
        db_path = str(tmp_path / "db" / "GeoLite2-City.mmdb")
        with patch.object(
            geo, "get_geo_lookup_maxmind_license_key", return_value="KEY"
        ), patch.object(
            geo, "get_geo_lookup_database_path", return_value=db_path
        ), patch.object(
            geo, "_download_maxmind_tarball", return_value=None
        ):
            assert geo.refresh_geolite_db() is False

    def test_makedirs_failure_returns_false(self, tmp_path):
        db_path = str(tmp_path / "db" / "GeoLite2-City.mmdb")
        with patch.object(
            geo, "get_geo_lookup_maxmind_license_key", return_value="KEY"
        ), patch.object(
            geo, "get_geo_lookup_database_path", return_value=db_path
        ), patch.object(
            geo.os, "makedirs", side_effect=OSError("no perms")
        ):
            assert geo.refresh_geolite_db() is False


# ---------------------------------------------------------------------
# geolite_refresh_service — background task
# ---------------------------------------------------------------------


class TestGeoliteRefreshService:
    @pytest.mark.asyncio
    async def test_runs_refresh_then_sleeps(self):
        # One iteration: enabled + key present -> refresh runs; sleep is
        # patched to break the loop via CancelledError.
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "get_geo_lookup_maxmind_license_key", return_value="KEY"
        ), patch.object(
            geo, "get_geo_lookup_refresh_interval_hours", return_value=24
        ), patch.object(
            geo.asyncio, "to_thread", return_value=None
        ) as to_thread, patch.object(
            geo.asyncio, "sleep", side_effect=asyncio_cancel()
        ):
            with pytest.raises(StopAsyncIteration):
                await geo.geolite_refresh_service()
        to_thread.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_refresh_when_no_key(self):
        with patch.object(
            geo, "is_geo_lookup_enabled", return_value=True
        ), patch.object(
            geo, "get_geo_lookup_maxmind_license_key", return_value=""
        ), patch.object(
            geo, "get_geo_lookup_refresh_interval_hours", return_value=24
        ), patch.object(
            geo.asyncio, "to_thread"
        ) as to_thread, patch.object(
            geo.asyncio, "sleep", side_effect=asyncio_cancel()
        ):
            with pytest.raises(StopAsyncIteration):
                await geo.geolite_refresh_service()
        to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_refresh_exception(self):
        # is_geo_lookup_enabled raising inside the try must not crash the
        # loop — it logs + proceeds to the sleep.
        with patch.object(
            geo, "is_geo_lookup_enabled", side_effect=RuntimeError("boom")
        ), patch.object(
            geo, "get_geo_lookup_refresh_interval_hours", return_value=24
        ), patch.object(
            geo.asyncio, "sleep", side_effect=asyncio_cancel()
        ):
            with pytest.raises(StopAsyncIteration):
                await geo.geolite_refresh_service()


async def asyncio_cancel_coro():
    raise StopAsyncIteration


def asyncio_cancel():
    """Return a side_effect that stops the infinite service loop cleanly.

    Raising StopAsyncIteration from the patched ``asyncio.sleep`` breaks the
    ``while True`` after exactly one iteration without a real sleep.
    """

    async def _stop(*_args, **_kwargs):
        raise StopAsyncIteration

    return _stop
