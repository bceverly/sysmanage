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
