# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The server's own clock, checked before it judges anyone else's (Phase 23.3).

Every host offset is measured RELATIVE TO THE SERVER.  A server whose clock is
itself off would report every host as off by the same amount -- or, worse,
hide a real skew behind its own.  So the server asks an NTP reference
(``time_sync.reference`` in sysmanage.yaml, default ``pool.ntp.org``) with a
single SNTP query, median of a few, cached for ``CACHE_SECONDS``.

An air-gapped server can name its internal NTP server, or set the reference
to ``""``: the result is then ``verified: False`` with the reason, never a
pretended "in sync".  Per process and cached: one tiny UDP exchange every few
minutes at most, on whichever worker is asked.
"""

from __future__ import annotations

import logging
import socket
import statistics
import struct
import threading
import time
from typing import Any, Dict, Optional

from backend.config import config

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE = "pool.ntp.org"
CACHE_SECONDS = 300
QUERIES = 3
TIMEOUT_S = 3.0
# The server's own clock is trusted to judge the fleet within this.
TRUST_MS = 100.0
_NTP_EPOCH = 2208988800

_cache: Dict[str, Any] = {}
_lock = threading.Lock()


def _reference() -> str:
    section = (config.get_config() or {}).get("time_sync") or {}
    ref = section.get("reference", DEFAULT_REFERENCE)
    return str(ref).strip() if ref is not None else ""


def sntp_offset_ms(server: str) -> Optional[float]:
    """This machine's clock minus ``server``'s, in ms (median of a few
    SNTP queries), or None when the server cannot be reached."""
    results = []
    for _ in range(QUERIES):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(TIMEOUT_S)
                t1 = time.time()
                sock.sendto(b"\x23" + 47 * b"\0", (server, 123))
                data, _ = sock.recvfrom(512)
                t4 = time.time()
        except OSError as exc:
            logger.debug("server clock: SNTP to %s failed: %s", server, exc)
            continue
        if len(data) < 48:
            continue
        recv_s, recv_f, tx_s, tx_f = struct.unpack("!IIII", data[32:48])
        t2 = recv_s - _NTP_EPOCH + recv_f / 2**32
        t3 = tx_s - _NTP_EPOCH + tx_f / 2**32
        # (reference - local); negated for local - reference.
        results.append(-((t2 - t1) + (t3 - t4)) / 2 * 1000)
    return round(statistics.median(results), 3) if results else None


def status(force: bool = False) -> Dict[str, Any]:
    """``{reference, offset_ms, verified, reason, checked_at}`` for the
    server's own clock.  ``verified`` is True only when a reference answered
    and the server is within ``TRUST_MS`` of it."""
    now = time.time()
    with _lock:
        if not force and _cache and now - _cache["checked_at"] < CACHE_SECONDS:
            return dict(_cache)
    reference = _reference()
    if not reference:
        result = _result(reference, None, "no_reference", now)
    else:
        offset = sntp_offset_ms(reference)
        if offset is None:
            result = _result(reference, None, "unreachable", now)
        elif abs(offset) > TRUST_MS:
            result = _result(reference, offset, "server_off", now)
            logger.warning(
                "The server's own clock is %s ms off %s: host clock offsets "
                "measured against it cannot be trusted until it is corrected",
                offset,
                reference,
            )
        else:
            result = _result(reference, offset, None, now)
    with _lock:
        _cache.clear()
        _cache.update(result)
    return dict(result)


def _result(reference, offset, reason, checked_at) -> Dict[str, Any]:
    return {
        "reference": reference or None,
        "offset_ms": offset,
        "verified": reason is None,
        "reason": reason,
        "checked_at": checked_at,
    }
