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


def _reply(reference_ahead_s, first=0x24, stratum=2, recv=None):
    """An NTP reply from a reference ``reference_ahead_s`` ahead of us:
    leap 0, version 4, mode 4 (0x24), stratum 2 -- unless told otherwise."""
    now = time.time() + reference_ahead_s + server_clock._NTP_EPOCH
    whole, frac = int(now), int((now % 1) * 2**32)
    recv_s = whole if recv is None else recv
    head = bytes([first, stratum]) + 30 * b"\0"
    return head + struct.pack("!IIII", recv_s, frac, whole, frac)


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


@pytest.mark.parametrize(
    "reply",
    [
        # Production 2026-11-18: a zero receive timestamp read as 63 years off.
        _reply(0.0, recv=0),
        _reply(0.0, stratum=0),  # a kiss-o'-death (RATE, DENY, ...)
        _reply(0.0, stratum=16),  # unsynchronized
        _reply(0.0, first=0xE4),  # leap indicator 3: the server is not synchronized
        _reply(0.0, first=0x23),  # mode 3: a client's packet, not a reply
    ],
    ids=["zero-receive", "kiss-of-death", "stratum-16", "leap-3", "client-mode"],
)
def test_an_unusable_reply_is_never_an_offset(reply):
    with patch.object(server_clock.socket, "socket", return_value=_Socket(reply)):
        assert server_clock.sntp_offset_ms("ntp.lab") is None


def test_unusable_replies_never_make_the_server_look_off():
    """One bad reply among good ones is left out, not averaged in."""
    replies = iter([_reply(0.0, recv=0), _reply(0.0), _reply(0.0)])

    class _Mixed(_Socket):
        def recvfrom(self, _n):
            return next(replies), ("ref", 123)

    with _config("ntp.lab"), patch.object(
        server_clock.socket, "socket", return_value=_Mixed()
    ):
        result = server_clock.status()
    assert result["verified"] is True and abs(result["offset_ms"]) < 50
