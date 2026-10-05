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


# -- a shared machine is not a measurement (2026-10-04) --------------------------


def _summary(**overrides):
    """A clean run's summary: every other criterion met."""
    base = {"expired_rows_final": 0, "auth_429": 0, "fallback_to_polling": 0,
            "register_gave_up": 0, "agents": 100, "connected_at_end": 100,
            "inbound_pending_final": 0, "inbound_pending_max": 0,
            "hosts_marked_down_max_after_restart": 0, "send_spike_ratio": None}  # fmt: skip
    base.update(overrides)
    return base


def test_an_oversubscribed_machine_marks_the_run_untrustworthy():
    out = fs.verdict(_summary(other_cpu_per_cpu_p90=0.6))
    assert out and out[0].startswith("RUN NOT TRUSTWORTHY")


def test_a_quiet_machine_adds_no_warning():
    out = fs.verdict(_summary(other_cpu_per_cpu_p90=0.05))
    assert not any("TRUSTWORTHY" in line for line in out)


def test_bsd_ps_cputime_is_parsed():
    from tests.load import observe  # pylint: disable=import-outside-toplevel

    parse = observe._cputime_seconds  # pylint: disable=protected-access
    assert parse("0:01.50") == 1.5
    assert parse("12:03.00") == 723
    assert parse("1:02:03.00") == 3723
    assert parse("2-01:00:00") == 2 * 86400 + 3600


def test_host_load_is_a_ratio_per_cpu():
    from tests.load import observe  # pylint: disable=import-outside-toplevel

    load = observe.host_load_per_cpu()
    assert load is None or load >= 0


def test_cpu_of_the_run_itself_is_not_other(monkeypatch):
    """The server tree, PostgreSQL and docker-proxy are the run; a browser
    is not."""
    from tests.load import observe  # pylint: disable=import-outside-toplevel

    tables = iter([
        {10: (1, "python", 0.0), 11: (10, "python", 0.0), 20: (1, "postgres", 0.0),
         21: (1, "docker-proxy", 0.0), 30: (1, "chrome", 0.0)},
        {10: (1, "python", 50.0), 11: (10, "python", 50.0), 20: (1, "postgres", 30.0),
         21: (1, "docker-proxy", 10.0), 30: (1, "chrome", 4.0)},
    ])  # fmt: skip
    clock = iter([100.0, 110.0])
    monkeypatch.setattr(observe, "_all_cpu_seconds", lambda: next(tables))
    monkeypatch.setattr(observe.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(observe.os, "cpu_count", lambda: 4)
    meter = observe.OtherCpu()
    assert meter.sample(10) is None  # the first sample only sets the baseline
    assert meter.sample(10) == 0.1  # chrome: 4 s of CPU in 10 s on 4 CPUs
