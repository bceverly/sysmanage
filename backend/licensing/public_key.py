# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Public key management for Pro+ license verification.

Downloads and caches the ECDSA P-521 public key from the license server.
Falls back to a cached copy if the server is unavailable.
"""

import os
from pathlib import Path
from typing import Optional

import aiohttp
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from backend.config.config import get_config
from backend.utils.verbosity_logger import get_logger

logger = get_logger("backend.licensing.public_key")

# Key metadata
KEY_ALGORITHM = "ES512"  # ECDSA with SHA-512
KEY_CURVE = "P-521"
KEY_VERSION = 1

# Cache file location
CACHE_DIR = Path("/var/lib/sysmanage/license")
CACHE_FILE = CACHE_DIR / "public_key.pem"

# In-memory cache using a dict to avoid global statement
_cache: dict = {"public_key": None}


def _cache_file() -> Path:
    """``license.public_key_path`` when set, else ``CACHE_FILE``.  With the
    cache read first (Phase 22.4), where it lives matters: a second server on
    one machine (the load-test stack, a self-signed test license) must not
    share -- or overwrite -- the installed server's key."""
    configured = (get_config().get("license") or {}).get("public_key_path")
    return Path(configured) if configured else CACHE_FILE


def _get_license_server_url() -> str:
    """Get the license server URL from config.

    The default value is supplied by backend.config.config when the
    config dict is built; no fallback string is needed (or wanted) here,
    since duplicating it risks drift between the two locations.
    """
    config = get_config()
    return config["license"]["phone_home_url"]


def _load_cached_key() -> Optional[str]:
    """Load public key from file cache."""
    if _cache["public_key"]:
        return _cache["public_key"]

    cache_file = _cache_file()
    if cache_file.exists():
        try:
            key_pem = cache_file.read_text()
        except Exception as e:
            logger.warning("Failed to read cached public key: %s", e)
            return None
        # A cached file that is not a key (damaged, truncated, another
        # server's leftovers) is treated as absent and refetched with one
        # warning -- it used to reach signature verification, which failed
        # with an ERROR and a traceback before the retry (2026-10-06).
        if not _is_public_key(key_pem):
            logger.warning(
                "Cached public key %s is not a valid PEM key; fetching a fresh one",
                cache_file,
            )
            return None
        _cache["public_key"] = key_pem
        logger.debug("Loaded public key from cache: %s", cache_file)
        return key_pem

    return None


def _is_public_key(key_pem: str) -> bool:
    try:
        load_pem_public_key(key_pem.encode("utf-8"))
        return True
    except (ValueError, TypeError, UnsupportedAlgorithm):
        return False


def _save_cached_key(key_pem: str) -> None:
    """Save public key to file cache."""
    cache_file = _cache_file()
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: a reader never sees a half-written key.
        partial = cache_file.with_name(f"{cache_file.name}.{os.getpid()}.tmp")
        partial.write_text(key_pem)
        os.replace(partial, cache_file)
        _cache["public_key"] = key_pem
        logger.info("Public key cached to: %s", cache_file)
    except Exception as e:
        logger.warning("Failed to cache public key: %s", e)
        # Still keep in memory
        _cache["public_key"] = key_pem


async def fetch_public_key() -> Optional[str]:
    """
    Fetch the public key from the license server.

    Returns:
        The public key in PEM format, or None if fetch failed
    """
    server_url = _get_license_server_url()
    key_url = f"{server_url.rstrip('/')}/v1/public-key"

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                key_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response,
        ):
            if response.status == 200:
                data = await response.json()
                public_key = data.get("public_key")
                if public_key:
                    _save_cached_key(public_key)
                    logger.info("Successfully fetched public key from license server")
                    return public_key
                else:
                    logger.error("License server returned empty public key")
            else:
                logger.warning("Failed to fetch public key: HTTP %d", response.status)
    except aiohttp.ClientError as e:
        logger.warning("Network error fetching public key: %s", e)
    except Exception as e:
        logger.exception("Unexpected error fetching public key: %s", e)

    return None


async def get_public_key_pem() -> Optional[str]:
    """
    Get the PEM-encoded public key for license verification.

    The cached key first, the license server only when there is none
    (Phase 22.4): every customer server fetched it on every start, so a
    fleet restarting together all called the license server at boot.  A key
    rotation is still picked up -- a license that does not verify against
    the cached key makes the caller fetch a fresh one
    (``license_service._validate_with_key``).

    Returns:
        The public key in PEM format, or None if unavailable
    """
    cached = _load_cached_key()
    if cached:
        return cached

    key = await fetch_public_key()
    if key:
        return key

    logger.error("No public key available - cannot validate licenses")
    return None


def get_public_key_pem_sync() -> Optional[str]:
    """
    Synchronous version - returns cached key only.

    For use in synchronous contexts where async is not available.

    Returns:
        The cached public key in PEM format, or None if not cached
    """
    return _load_cached_key()


def get_key_metadata() -> dict:
    """
    Get metadata about the public key.

    Returns:
        Dictionary with key algorithm, curve, and version
    """
    return {
        "algorithm": KEY_ALGORITHM,
        "curve": KEY_CURVE,
        "version": KEY_VERSION,
    }


def clear_cache() -> None:
    """Clear the in-memory and file cache."""
    _cache["public_key"] = None

    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
            logger.info("Public key cache cleared")
        except Exception as e:
            logger.warning("Failed to delete cache file: %s", e)
