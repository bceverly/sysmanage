# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Phase 22.2: right after the server starts, silence is the server's own
outage, not the hosts' -- nobody is marked down until agents had time to
reconnect.  (The scale harness's restart storm marked hosts down without it.)"""

from unittest.mock import MagicMock, patch

import pytest

from backend.monitoring import heartbeat_monitor as hm


def test_no_grace_when_the_service_has_not_started():
    assert not hm._in_outage_grace(5, now=1e9)


def test_grace_lasts_a_heartbeat_window_plus_reconnect_time():
    hm._service_started_at = 1000.0
    window = 60 * (5 + hm.RECONNECT_ALLOWANCE_MINUTES)
    assert hm._in_outage_grace(5, now=1000.0 + window - 1)
    assert not hm._in_outage_grace(5, now=1000.0 + window)


@pytest.mark.asyncio
async def test_nothing_is_marked_down_during_the_grace():
    db = MagicMock()
    mark = MagicMock()
    with patch.multiple(
        hm,
        iter_host_databases=MagicMock(return_value=[("bootstrap", None, db)]),
        get_heartbeat_timeout_minutes=MagicMock(return_value=5),
        _mark_stale_hosts_down=mark,
        _in_outage_grace=MagicMock(return_value=True),
    ):
        await hm.check_host_heartbeats()
    mark.assert_not_called()
    db.close.assert_called_once()


@pytest.mark.asyncio
async def test_after_the_grace_stale_hosts_are_marked():
    db = MagicMock()
    mark = MagicMock()
    with patch.multiple(
        hm,
        iter_host_databases=MagicMock(return_value=[("bootstrap", None, db)]),
        get_heartbeat_timeout_minutes=MagicMock(return_value=5),
        _mark_stale_hosts_down=mark,
        _in_outage_grace=MagicMock(return_value=False),
    ):
        await hm.check_host_heartbeats()
    mark.assert_called_once()
