# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Every host refreshes its OWN catalog, daily.

Two failures motivate this service, and the tests below pin both.

1. NOTHING refreshed the catalog.  A host was asked for its packages once --
   when it had no rows -- and never again, so ``available_packages`` froze at
   whatever the machine offered on the day it enrolled.  The gap was hidden
   because a field-comparison bug made the "no rows" trigger fire forever; that
   was 9.4 GB of waste, but it did keep the data fresh.  Fixing it removed the
   accidental refresh too.

2. There is NO canonical package list for an operating system.  Two Ubuntu
   26.04 machines legitimately differ: one carries a PPA, another points at an
   internal mirror, a third has universe disabled.  Sampling one "best" host
   and storing its catalog as the OS's would publish that host's repositories
   as everyone's -- offering packages the other machines cannot install.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.services.package_catalog_refresh import (
    DEFAULT_INTERVAL_SECONDS,
    STALE_AFTER_HOURS,
    _needs_refresh,
    request_refresh_for_stale_hosts,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class _Host:
    def __init__(self, fqdn, fingerprint=None, reported=None):
        self.id = f"id-{fqdn}"
        self.fqdn = fqdn
        self.available_packages_fingerprint = fingerprint
        self.available_packages_fingerprint_at = reported


# --------------------------------------------------------------------------
# staleness
# --------------------------------------------------------------------------


def test_host_that_never_delivered_is_always_asked():
    """No fingerprint means no catalog ever landed -- the most obvious gap."""
    assert _needs_refresh(_Host("new.x"), NOW) is True


def test_fingerprint_without_a_timestamp_is_asked():
    """Defensive: a half-written row must not be silently skipped for ever."""
    assert _needs_refresh(_Host("odd.x", fingerprint="abc"), NOW) is True


def test_fresh_host_is_left_alone():
    host = _Host("fresh.x", "abc", NOW - timedelta(hours=1))
    assert _needs_refresh(host, NOW) is False


def test_stale_host_is_asked():
    host = _Host("stale.x", "abc", NOW - timedelta(hours=STALE_AFTER_HOURS + 1))
    assert _needs_refresh(host, NOW) is True


def test_naive_timestamps_are_treated_as_utc():
    """The DB hands back naive datetimes; comparing them must not explode."""
    host = _Host("naive.x", "abc", (NOW - timedelta(hours=1)).replace(tzinfo=None))
    assert _needs_refresh(host, NOW) is False


def test_staleness_window_is_under_the_interval():
    """Otherwise a pass running minutes early skips a host for a whole day."""
    assert STALE_AFTER_HOURS * 3600 < DEFAULT_INTERVAL_SECONDS


# --------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------


def _session_with(hosts):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = hosts
    return session


@pytest.fixture(name="queued")
def _queued():
    """Capture what would be enqueued, per host."""
    with patch("backend.websocket.queue_manager.server_queue_manager") as queue, patch(
        "backend.websocket.messages.create_command_message"
    ) as make:
        make.side_effect = lambda command_type, parameters: {
            "command_type": command_type,
            "parameters": parameters,
        }
        yield queue


def test_every_stale_host_is_asked_individually(queued):
    """The core of the fix: per HOST, not one representative per OS.

    Three Ubuntu machines with different repositories must each be asked for
    their own catalog.
    """
    hosts = [
        _Host("ppa-box.x", "f1", NOW - timedelta(days=2)),
        _Host("mirror-box.x", "f2", NOW - timedelta(days=2)),
        _Host("plain-box.x", "f3", NOW - timedelta(days=2)),
    ]
    asked = request_refresh_for_stale_hosts(_session_with(hosts), MagicMock(), NOW)
    assert asked == 3
    assert queued.enqueue_message.call_count == 3
    targets = {c.kwargs["host_id"] for c in queued.enqueue_message.call_args_list}
    assert targets == {h.id for h in hosts}


def test_each_host_is_handed_ITS_OWN_fingerprint(queued):
    """A shared or wrong fingerprint would defeat the whole handshake.

    The server holds a different catalog per host, so the base it offers must
    be that host's -- otherwise every host reports a mismatch and sends a full
    catalog, which is the cost this service is designed to avoid.
    """
    hosts = [
        _Host("a.x", "fingerprint-A", NOW - timedelta(days=2)),
        _Host("b.x", "fingerprint-B", NOW - timedelta(days=2)),
    ]
    request_refresh_for_stale_hosts(_session_with(hosts), MagicMock(), NOW)

    sent = {
        c.kwargs["host_id"]: c.kwargs["message_data"]["parameters"]["known_fingerprint"]
        for c in queued.enqueue_message.call_args_list
    }
    assert sent == {"id-a.x": "fingerprint-A", "id-b.x": "fingerprint-B"}


def test_fresh_hosts_are_not_asked(queued):
    hosts = [
        _Host("fresh.x", "f1", NOW - timedelta(hours=1)),
        _Host("stale.x", "f2", NOW - timedelta(days=3)),
    ]
    asked = request_refresh_for_stale_hosts(_session_with(hosts), MagicMock(), NOW)
    assert asked == 1
    assert queued.enqueue_message.call_args_list[0].kwargs["host_id"] == "id-stale.x"


def test_one_unqueueable_host_does_not_stop_the_others(queued):
    """A single bad host must not leave the rest of the fleet unrefreshed."""
    queued.enqueue_message.side_effect = [RuntimeError("boom"), None, None]
    hosts = [_Host(f"h{i}.x", f"f{i}", NOW - timedelta(days=2)) for i in range(3)]
    asked = request_refresh_for_stale_hosts(_session_with(hosts), MagicMock(), NOW)
    assert asked == 2
    assert queued.enqueue_message.call_count == 3


def test_nothing_is_asked_when_the_fleet_is_current(queued):
    hosts = [_Host(f"h{i}.x", f"f{i}", NOW - timedelta(minutes=5)) for i in range(4)]
    assert request_refresh_for_stale_hosts(_session_with(hosts), MagicMock(), NOW) == 0
    queued.enqueue_message.assert_not_called()
