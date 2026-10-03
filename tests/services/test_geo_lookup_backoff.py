# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.3: geolocation lookups that do not hammer anyone.

* ipapi.co's free tier is 1,000 lookups a day for the server's address; a 429
  pauses every lookup (Retry-After, else an hour) instead of the next host
  asking at once.
* An address that resolved to nothing is not asked again for six hours --
  every connect of a host behind an unknown NAT asked again.
* The GeoLite2 file is downloaded only when it is stale, not on every start.
"""

import os
import time
from types import SimpleNamespace
from unittest.mock import patch

from backend.services import geolocation_service as geo

PUBLIC_IP = "8.8.8.8"
GEO = "backend.services.geolocation_service"


def _response(status, headers=None, body=None):
    return SimpleNamespace(status_code=status, headers=headers or {},
                           json=lambda: body or {})  # fmt: skip


def _enabled():
    return (patch(f"{GEO}.is_geo_lookup_enabled", return_value=True),
            patch(f"{GEO}.is_geo_lookup_ipapi_fallback_enabled", return_value=True),
            patch(f"{GEO}._lookup_via_geolite2", return_value=None))  # fmt: skip


def test_a_429_pauses_every_lookup():
    a, b, c = _enabled()
    with a, b, c, patch(f"{GEO}.httpx.get",
                        return_value=_response(429, {"Retry-After": "600"})) as get:  # fmt: skip
        assert geo.lookup_ip(PUBLIC_IP) is None
        assert geo.lookup_ip("1.1.1.1") is None  # another host: not asked
        assert geo.lookup_ip("9.9.9.9") is None
    assert get.call_count == 1


def test_the_pause_ends():
    a, b, c = _enabled()
    with a, b, c, patch(f"{GEO}.httpx.get", return_value=_response(429)):
        geo.lookup_ip(PUBLIC_IP)
    geo._ipapi_paused_until = time.monotonic() - 1  # pylint: disable=protected-access
    ok = _response(200, body={"country_code": "us"})
    with a, b, c, patch(f"{GEO}.httpx.get", return_value=ok) as get:
        assert geo.lookup_ip("1.1.1.1").country_code == "US"
    assert get.call_count == 1


def test_an_address_that_resolved_to_nothing_is_not_asked_again_soon():
    a, b, c = _enabled()
    with a, b, c, patch(f"{GEO}.httpx.get",
                        return_value=_response(200, body={"error": True})) as get:  # fmt: skip
        for _ in range(5):
            assert geo.lookup_ip(PUBLIC_IP) is None
    assert get.call_count == 1


def test_a_resolved_address_is_not_cached_as_a_miss():
    a, b, c = _enabled()
    ok = _response(200, body={"country_code": "de"})
    with a, b, c, patch(f"{GEO}.httpx.get", return_value=ok) as get:
        geo.lookup_ip(PUBLIC_IP)
        geo.lookup_ip(PUBLIC_IP)
    assert get.call_count == 2  # callers decide when to ask again


def test_geolite_is_downloaded_only_when_stale(tmp_path):
    path = tmp_path / "GeoLite2-City.mmdb"
    with patch(f"{GEO}.get_geo_lookup_database_path", return_value=str(path)), patch(
        f"{GEO}.get_geo_lookup_refresh_interval_hours", return_value=168
    ):
        assert geo.geolite_is_stale()  # missing
        path.write_bytes(b"x")
        assert not geo.geolite_is_stale()  # fresh: a restart does not re-download
        old = time.time() - 168 * 3600
        os.utime(path, (old, old))
        assert geo.geolite_is_stale()
