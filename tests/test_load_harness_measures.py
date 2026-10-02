# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The scale harness's own arithmetic (Phase 22).

A wrong measurement is worse than none: on 2026-10-02 the reconnect time read
0.1 s because the first samples after the restart still counted the old
connections, which also shrank the window the spike ratio leaves out and
failed a run that had met every criterion.
"""

from tests.load import fleet_scenarios as fs


def _timeline(points):
    return [{"t": t, "connected": c, "sent_since_last": s} for t, c, s in points]


def test_reconnect_waits_for_the_drop_before_timing_the_recovery():
    timeline = _timeline([(299, 1000, 5), (300.1, 1000, 5), (305, 0, 0),
                          (330, 600, 900), (390, 990, 300), (400, 1000, 20)])  # fmt: skip
    assert (
        fs._reconnect_seconds(timeline, 300, 1000) == 90
    )  # pylint: disable=protected-access


def test_no_drop_means_no_reconnect_figure():
    timeline = _timeline([(301, 1000, 5), (330, 1000, 5)])
    assert (
        fs._reconnect_seconds(timeline, 300, 1000) is None
    )  # pylint: disable=protected-access


def test_the_restart_surge_is_left_out_of_the_spike_ratio():
    steady = [(t, 1000, 10) for t in range(310, 300 + 600, 10) if not 300 < t < 460]
    surge = [(305, 0, 0), (330, 600, 900), (390, 990, 300)]
    timeline = _timeline(sorted(steady + surge))
    window = fs._restart_window(timeline, 300, 1000)  # pylint: disable=protected-access
    assert (
        fs._spike_ratio(timeline, 0, window) == 1.0
    )  # pylint: disable=protected-access
