"""
Public key management for Pro+ license verification.

Downloads and caches the ECDSA P-521 public key from the license server.
Falls back to a cached copy if the server is unavailable.
"""

import os
from pathlib import Path
from typing import Optional

import aiohttp

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


def _get_license_server_url() -> str:
    """Get the license server URL from config."""
    config = get_config()
    license_config = config.get("license", {})
    return license_config.get("phone_home_url", "https://license.sysmanage.io")


def _load_cached_key() -> Optional[str]:
    """Load public key from file cache."""
    if _cache["public_key"]:
        return _cache["public_key"]

    if CACHE_FILE.exists():
        try:
            _cache["public_key"] = CACHE_FILE.read_text()
            logger.debug("Loaded public key from cache: %s", CACHE_FILE)
            return _cache["public_key"]
        except Exception as e:
            logger.warning("Failed to read cached public key: %s", e)

    return None


def _save_cached_key(key_pem: str) -> None:
    """Save public key to file cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(key_pem)
        _cache["public_key"] = key_pem
        logger.info("Public key cached to: %s", CACHE_FILE)
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
        async with aiohttp.ClientSession() as session:
            async with session.get(
                key_url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    public_key = data.get("public_key")
                    if public_key:
                        _save_cached_key(public_key)
                        logger.info(
                            "Successfully fetched public key from license server"
                        )
                        return public_key
                    else:
                        logger.error("License server returned empty public key")
                else:
                    logger.warning(
                        "Failed to fetch public key: HTTP %d", response.status
                    )
    except aiohttp.ClientError as e:
        logger.warning("Network error fetching public key: %s", e)
    except Exception as e:
        logger.error("Unexpected error fetching public key: %s", e)

    return None


async def get_public_key_pem() -> Optional[str]:
    """
    Get the PEM-encoded public key for license verification.

    First tries to fetch from the license server, then falls back to cache.

    Returns:
        The public key in PEM format, or None if unavailable
    """
    # Try to fetch fresh key from server
    key = await fetch_public_key()
    if key:
        return key

    # Fall back to cached key
    cached = _load_cached_key()
    if cached:
        logger.info("Using cached public key (server unavailable)")
        return cached

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
