"""
Phase 12.7: Host geo-location service.

Standalone module providing IP -> (country, subdivision, city, lat, lon)
lookups via a bundled MaxMind GeoLite2-City database with an
ipapi.co fallback only when the local DB misses.

Designed to be consumed by:
  * the heartbeat handler (per-host public-IP -> geo resolution
    cached on the Host row)
  * the future ``federation_controller_engine`` (cross-site rollup of
    the same geo data)

Privacy / safety:
  * Private / link-local / loopback / reserved IPs short-circuit to
    None — no upstream lookup, no MaxMind read.  RFC 1918, RFC 6598
    (CGNAT 100.64/10), IPv6 ULA, link-local are all caught here.
  * The per-deployment ``geo_lookup.enabled`` config flag (default
    True) disables the whole chain when False — airgapped deployments
    and privacy-conscious operators leave it off.
  * No reverse-geocoding of internal IPs ever happens — those would
    resolve to NAT egress IPs (already known from the site-server row
    in federation contexts) or to garbage.

License:
  * GeoLite2-City is MaxMind's free tier, distributed under
    CC BY-SA 4.0.  Operator supplies a free MaxMind license key via
    ``geo_lookup.maxmind_license_key``; weekly download via
    ``download.maxmind.com``.  Without a license key, lookups fall
    back entirely to ipapi.co (1000 req/day free tier) and degrade
    silently to ``country=unknown`` when the rate-limit is exhausted.

This module is intentionally standalone (no federation imports,
no Pro+ engine imports) so single-server deployments and federation
deployments consume the same code path.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import shutil
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from backend.config.config import (
    get_geo_lookup_database_path,
    get_geo_lookup_maxmind_license_key,
    get_geo_lookup_refresh_interval_hours,
    is_geo_lookup_enabled,
    is_geo_lookup_ipapi_fallback_enabled,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Privacy opt-out tag
# ---------------------------------------------------------------------

# A host carrying this tag is excluded from BOTH geo-resolution
# (heartbeat handler skips the MaxMind / ipapi.co lookup) AND the
# world-map endpoint (excluded from /api/hosts/geolocations).  Two
# call-sites import this constant so the name stays in lockstep:
#   * ``backend/api/message_handlers_core.py`` (heartbeat path)
#   * ``backend/api/host.py`` (map endpoint)
# Operators set it by adding the tag named below to a host via the
# Hosts UI / API; no separate config flag required.
NO_GEO_TRACK_TAG = "no_geo_track"


# ---------------------------------------------------------------------
# Public data shape
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class GeoResult:
    """Resolved geographic location for an IP address.

    All optional except ``country_code`` — the GeoLite2 database always
    has a country mapping even when subdivision / city are unavailable
    (e.g., for satellite-allocated IP blocks).  ``source`` documents
    which backend produced the result for audit / diagnostics.
    """

    country_code: str  # ISO 3166-1 alpha-2, e.g. "US", "DE", "JP"
    subdivision_code: Optional[str]  # ISO 3166-2, e.g. "US-CA", "DE-BY"
    city: Optional[str]  # MaxMind canonical English name
    latitude: Optional[float]
    longitude: Optional[float]
    source: str  # "geolite2" | "ipapi"


# ---------------------------------------------------------------------
# Private IP detection
# ---------------------------------------------------------------------

# RFC 6598 CGNAT block (100.64.0.0/10).  Some Python versions' built-in
# ``ipaddress.IPv4Address.is_private`` doesn't include this range, so we
# check it explicitly.  ULA (fc00::/7) and IPv6 link-local (fe80::/10)
# ARE caught by ``is_private`` / ``is_link_local`` on all supported
# Python versions.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def is_internal_ip(ip_str: str) -> bool:
    """True if the IP is a private, link-local, loopback, reserved, or CGNAT address.

    Used to short-circuit lookup for IPs that have no public-internet
    geo meaning.  Per the Phase 12.7 ROADMAP design, internal IPs are
    silently skipped — they'd resolve to either nonsense or to the
    site-server's NAT egress (already known elsewhere).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except (ValueError, TypeError):
        # Malformed input — treat as internal (i.e. skip).  We never
        # forward malformed strings to MaxMind or ipapi.co.
        return True

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    # CGNAT range — explicit because some stdlib versions miss it.
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return True
    return False


# ---------------------------------------------------------------------
# GeoLite2 reader management
# ---------------------------------------------------------------------


class _GeoLite2ReaderHolder:
    """Thread-safe holder for the open ``geoip2.database.Reader``.

    The reader is opened lazily on first lookup and re-opened after a
    successful background refresh.  All reads go through ``with_reader``
    which yields the current reader under a read-lock; writes (close +
    reopen after refresh) acquire the write-lock.

    geoip2's Reader is documented as thread-safe for concurrent
    ``.city()`` reads, so the read-lock is only needed to guard against
    the writer mid-swap.
    """

    def __init__(self) -> None:
        self._reader = None
        self._reader_path: Optional[str] = None
        self._lock = threading.RLock()

    def get_reader(self):
        """Return the current Reader, opening it if needed.  None if open fails."""
        with self._lock:
            db_path = get_geo_lookup_database_path()
            if self._reader is not None and self._reader_path == db_path:
                return self._reader
            # Open or re-open.
            if self._reader is not None:
                try:
                    self._reader.close()
                except (
                    Exception
                ):  # nosec B110 - best-effort close before reopen; the new Reader replaces it regardless  # pylint: disable=broad-exception-caught
                    pass
                self._reader = None
            if not os.path.isfile(db_path):
                logger.debug(
                    "GeoLite2 database not present at %s; lookups will fall back to ipapi.co",
                    db_path,
                )
                return None
            try:
                import geoip2.database  # noqa: PLC0415

                self._reader = geoip2.database.Reader(db_path)
                self._reader_path = db_path
                logger.info("Opened GeoLite2 database at %s", db_path)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "Failed to open GeoLite2 database at %s: %s; lookups will fall back to ipapi.co",
                    db_path,
                    exc,
                )
                self._reader = None
                self._reader_path = None
            return self._reader

    def close(self) -> None:
        """Close the current Reader (called from teardown + after refresh)."""
        with self._lock:
            if self._reader is not None:
                try:
                    self._reader.close()
                except (
                    Exception
                ):  # nosec B110 - teardown path; nothing else can recover if close() raises  # pylint: disable=broad-exception-caught
                    pass
                self._reader = None
                self._reader_path = None


_reader_holder = _GeoLite2ReaderHolder()


def _lookup_via_geolite2(ip_str: str) -> Optional[GeoResult]:
    """Resolve ``ip_str`` against the bundled GeoLite2 database.

    Returns None if the DB isn't open, isn't found, or doesn't contain
    a record for the IP (e.g. very new IP allocations not yet in the
    weekly DB drop).  Callers fall back to ipapi.co in that case.
    """
    reader = _reader_holder.get_reader()
    if reader is None:
        return None
    try:
        import geoip2.errors  # noqa: PLC0415

        response = reader.city(ip_str)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # geoip2.errors.AddressNotFoundError is the expected "no record"
        # case; any other exception is a logged miss + fall through.
        if exc.__class__.__name__ != "AddressNotFoundError":
            logger.debug("GeoLite2 lookup error for %s: %s", ip_str, exc)
        return None

    country_code = (response.country.iso_code or "").upper()
    if not country_code:
        # No country at all -> not useful.  Fall through to fallback.
        return None
    subdivision_code: Optional[str] = None
    if response.subdivisions and response.subdivisions.most_specific.iso_code:
        sub = response.subdivisions.most_specific.iso_code.upper()
        subdivision_code = f"{country_code}-{sub}"
    return GeoResult(
        country_code=country_code,
        subdivision_code=subdivision_code,
        city=response.city.name,
        latitude=(
            float(response.location.latitude)
            if response.location.latitude is not None
            else None
        ),
        longitude=(
            float(response.location.longitude)
            if response.location.longitude is not None
            else None
        ),
        source="geolite2",
    )


# ---------------------------------------------------------------------
# ipapi.co fallback
# ---------------------------------------------------------------------

_IPAPI_URL_TEMPLATE = "https://ipapi.co/{ip}/json/"
_IPAPI_TIMEOUT_SECONDS = 5.0


def _lookup_via_ipapi(ip_str: str) -> Optional[GeoResult]:
    """Resolve ``ip_str`` via ipapi.co's free tier.

    Returns None on timeout, network error, rate-limit, or malformed
    response.  Per the ROADMAP, this degrades silently rather than
    raising — callers treat None as "unknown location" and leave the
    host's geo columns at their previous value (or NULL).
    """
    if not is_geo_lookup_ipapi_fallback_enabled():
        return None
    url = _IPAPI_URL_TEMPLATE.format(ip=ip_str)
    try:
        response = httpx.get(url, timeout=_IPAPI_TIMEOUT_SECONDS)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.debug("ipapi.co fallback network error for %s: %s", ip_str, exc)
        return None
    if response.status_code != 200:
        # 429 = rate-limited; other non-200s shouldn't normally happen.
        logger.debug(
            "ipapi.co fallback returned HTTP %d for %s", response.status_code, ip_str
        )
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    # ipapi.co returns ``error: true`` on rate-limit hits and a few
    # other failures.  Treat as a miss.
    if data.get("error"):
        logger.debug("ipapi.co fallback returned error payload for %s", ip_str)
        return None
    country_code = (data.get("country_code") or "").upper()
    if not country_code:
        return None
    region_code = data.get("region_code")
    subdivision_code = f"{country_code}-{region_code.upper()}" if region_code else None
    lat = data.get("latitude")
    lon = data.get("longitude")
    return GeoResult(
        country_code=country_code,
        subdivision_code=subdivision_code,
        city=data.get("city"),
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        source="ipapi",
    )


# ---------------------------------------------------------------------
# Public lookup entrypoint
# ---------------------------------------------------------------------


def lookup_ip(ip_str: str) -> Optional[GeoResult]:
    """Resolve a public IP to (country, subdivision, city, lat, lon).

    Returns None when:
      * geo_lookup is disabled at the deployment level;
      * the input is malformed or an internal-range IP (private,
        loopback, link-local, reserved, CGNAT);
      * both GeoLite2 and ipapi.co miss / fail.

    Callers MUST treat None as "no update" — do not blank out
    previously-resolved geo columns just because a single lookup
    didn't find anything.

    Lookup chain: GeoLite2 (local, fast, free) -> ipapi.co (network,
    rate-limited).  If ipapi.co is disabled (``geo_lookup.ipapi_fallback_enabled = false``)
    only the local DB is consulted.
    """
    if not is_geo_lookup_enabled():
        return None
    if not ip_str or not isinstance(ip_str, str):
        return None
    ip_str = ip_str.strip()
    if is_internal_ip(ip_str):
        return None

    result = _lookup_via_geolite2(ip_str)
    if result is not None:
        return result
    return _lookup_via_ipapi(ip_str)


# ---------------------------------------------------------------------
# GeoLite2 weekly refresh
# ---------------------------------------------------------------------

_MAXMIND_DOWNLOAD_URL = (
    "https://download.maxmind.com/app/geoip_download"
    "?edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz"
)
_DOWNLOAD_TIMEOUT_SECONDS = 300.0  # 75MB on a slow link


def refresh_geolite_db() -> bool:
    """Download + install the latest GeoLite2-City DB.  Returns True on success.

    Synchronous (network + filesystem only).  The background-task
    wrapper ``geolite_refresh_service`` below schedules calls to this
    function at the configured interval.

    Atomic-replace semantics: download to a temp file, extract to a
    temp dir, then ``os.replace`` the .mmdb into place and close+reopen
    the Reader.  A failed download / extract leaves the previous DB
    untouched.
    """
    license_key = get_geo_lookup_maxmind_license_key()
    if not license_key:
        logger.debug("MaxMind license key not configured; skipping GeoLite2 refresh")
        return False

    db_path = get_geo_lookup_database_path()
    db_dir = os.path.dirname(db_path) or "."
    try:
        os.makedirs(db_dir, exist_ok=True)
    except OSError as exc:
        logger.warning("Cannot create GeoLite2 directory %s: %s", db_dir, exc)
        return False

    url = _MAXMIND_DOWNLOAD_URL.format(key=license_key)
    logger.info("Refreshing GeoLite2-City database from MaxMind")
    try:
        with httpx.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            if response.status_code != 200:
                logger.warning(
                    "MaxMind download returned HTTP %d; keeping existing DB",
                    response.status_code,
                )
                return False
            with tempfile.NamedTemporaryFile(
                suffix=".tar.gz", dir=db_dir, delete=False
            ) as tmp_tarball:
                tarball_path = tmp_tarball.name
                for chunk in response.iter_bytes(chunk_size=65536):
                    tmp_tarball.write(chunk)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.warning("MaxMind download network error: %s", exc)
        return False

    # Extract — the tarball contains a dated directory with the .mmdb
    # inside (e.g. ``GeoLite2-City_20260518/GeoLite2-City.mmdb``).  We
    # find the .mmdb by walking the extracted tree rather than guessing
    # the date prefix.
    try:
        with tempfile.TemporaryDirectory(dir=db_dir) as extract_dir:
            with tarfile.open(tarball_path, "r:gz") as tar:
                # Verify members don't escape the extract dir before
                # extracting — defense in depth even though MaxMind's
                # tarballs are well-formed.
                base = Path(extract_dir).resolve()
                for member in tar.getmembers():
                    target = (base / member.name).resolve()
                    if not str(target).startswith(str(base) + os.sep):
                        logger.warning(
                            "MaxMind tarball contained suspicious path %s; aborting",
                            member.name,
                        )
                        return False
                tar.extractall(extract_dir)  # nosec B202  # path-validated above
            # Locate the .mmdb file
            mmdb_path = None
            for root, _dirs, files in os.walk(extract_dir):
                for fname in files:
                    if fname.endswith(".mmdb"):
                        mmdb_path = os.path.join(root, fname)
                        break
                if mmdb_path:
                    break
            if mmdb_path is None:
                logger.warning(
                    "MaxMind tarball did not contain a .mmdb file; keeping existing DB"
                )
                return False
            # Atomic replace into the configured location.  Close the
            # current reader BEFORE the replace so Windows (which can't
            # replace open files) doesn't EACCES.
            _reader_holder.close()
            shutil.move(mmdb_path, db_path)
            logger.info("GeoLite2-City database refreshed to %s", db_path)
            # Trigger reopen on next lookup (lazy).
            return True
    except (tarfile.TarError, OSError) as exc:
        logger.warning("MaxMind tarball extraction error: %s", exc)
        return False
    finally:
        try:
            os.unlink(tarball_path)
        except OSError:
            pass


async def geolite_refresh_service() -> None:
    """Background task: refresh the GeoLite2 DB at the configured interval.

    Started by the lifecycle hook in ``backend/startup/lifecycle.py``
    (added in a follow-up step).  Runs ``refresh_geolite_db`` then
    sleeps; safe to cancel at any point — there's no in-flight state
    to recover.

    Skips work entirely (just sleeps) if geo_lookup is disabled or no
    MaxMind license key is configured — those operators don't want
    weekly downloads they can't use.
    """
    while True:
        try:
            if is_geo_lookup_enabled() and get_geo_lookup_maxmind_license_key():
                # Run the (synchronous) refresh in a thread so we don't
                # block the asyncio event loop for the duration of a
                # 75MB download.
                await asyncio.to_thread(refresh_geolite_db)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("GeoLite2 refresh task iteration failed: %s", exc)
        # Sleep until the next configured refresh window.
        sleep_seconds = max(1, get_geo_lookup_refresh_interval_hours() * 3600)
        await asyncio.sleep(sleep_seconds)
