# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The server's own clock against its reference (Phase 23.3 S2)."""

import struct
import time
from unittest.mock import patch

import pytest

from backend.services import server_clock


@pytest.fixture(autouse=True)
def _no_cache():
    server_clock._cache.clear()
    yield
    server_clock._cache.clear()


def _reply(reference_ahead_s):
    """An NTP reply from a reference ``reference_ahead_s`` ahead of us."""
    now = time.time() + reference_ahead_s + server_clock._NTP_EPOCH
    whole, frac = int(now), int((now % 1) * 2**32)
    return b"\x24" + 31 * b"\0" + struct.pack("!IIII", whole, frac, whole, frac)


class _Socket:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, _t):
        pass

    def sendto(self, _data, _addr):
        if self.error:
            raise self.error

    def recvfrom(self, _n):
        return self.reply, ("ref", 123)


def _config(reference):
    section = {} if reference is ... else {"time_sync": {"reference": reference}}
    return patch.object(server_clock.config, "get_config", return_value=section)


def test_a_server_close_to_its_reference_is_verified():
    with _config(...), patch.object(
        server_clock.socket, "socket", return_value=_Socket(_reply(0.0))
    ):
        result = server_clock.status()
    assert result["reference"] == "pool.ntp.org"
    assert result["verified"] is True and result["reason"] is None
    assert abs(result["offset_ms"]) < 50


def test_a_server_far_off_its_reference_is_not_trusted():
    with _config("ntp.lab"), patch.object(
        server_clock.socket, "socket", return_value=_Socket(_reply(-2.0))
    ):
        result = server_clock.status()
    assert result["reason"] == "server_off" and result["verified"] is False
    assert result["offset_ms"] == pytest.approx(2000, abs=50)  # we are AHEAD


def test_unreachable_and_absent_references_are_never_in_sync():
    with _config("ntp.lab"), patch.object(
        server_clock.socket, "socket", return_value=_Socket(error=OSError("no"))
    ):
        assert server_clock.status()["reason"] == "unreachable"
    with _config(""):
        result = server_clock.status(force=True)
    assert (result["reference"], result["reason"]) == (None, "no_reference")
    with _config(None):
        assert server_clock.status(force=True)["reason"] == "no_reference"


def test_a_short_reply_is_ignored():
    with patch.object(
        server_clock.socket, "socket", return_value=_Socket(b"\x24" * 10)
    ):
        assert server_clock.sntp_offset_ms("ntp.lab") is None


def test_the_result_is_cached():
    with _config(""):
        first = server_clock.status()
    with _config("ntp.lab"), patch.object(server_clock.socket, "socket") as sock:
        assert server_clock.status() == first
        sock.assert_not_called()
