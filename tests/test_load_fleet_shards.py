# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The scale harness's fleet shards (Phase 22): several simulator processes
on several machines, merged into one report."""

import pytest

from tests.load import fleet_shards as fs


def test_one_host_is_one_shard_as_before():
    assert fs.split("freebsd", 10_000) == [fs.Shard("freebsd", 0, 10_000)]


def test_agents_spread_evenly_with_unique_ranges():
    shards = fs.split("t14:2,freebsd,t480:2", 50_001)
    assert [s.host for s in shards] == ["t14", "t14", "freebsd", "t480", "t480"]
    assert sum(s.count for s in shards) == 50_001
    assert max(s.count for s in shards) - min(s.count for s in shards) <= 1
    ranges = [range(s.first, s.first + s.count) for s in shards]
    assert sorted(i for r in ranges for i in r) == list(range(50_001))


def test_more_processes_than_agents_skips_empty_shards():
    assert len(fs.split("a:4", 2)) == 2


@pytest.mark.parametrize("spec", ["", "a:0", ":2", " , "])
def test_bad_specs_are_refused(spec):
    with pytest.raises(ValueError):
        fs.split(spec, 10)


def _part(agents, connected, rtts, rows):
    return {"agents": agents, "time_scale": 1.0, "connected_at_end": connected,
            "bytes_sent": 100, "heartbeat_rtt_ms": rtts, "report_windows": [],
            "counts": {"connect_ok": connected}, "sent": {"heartbeat": 2},
            "errors_received": {},
            "timeline": [{"t": 5.0 * i, "connected": connected, "polling": 0,
                          "sent_since_last": 1, "auth_429_total": 0,
                          "connect_ok_total": connected} for i in range(rows)]}  # fmt: skip


def test_merge_sums_counts_and_timelines():
    merged = fs.merge([_part(10, 9, [1.0], 3), _part(20, 18, [2.0, 3.0], 2)])
    assert merged["agents"] == 30 and merged["connected_at_end"] == 27
    assert merged["counts"]["connect_ok"] == 27 and merged["sent"]["heartbeat"] == 4
    assert merged["heartbeat_rtt_ms"] == [1.0, 2.0, 3.0]
    assert len(merged["timeline"]) == 2
    assert merged["timeline"][1] == {"t": 5.0, "connected": 27, "polling": 0,
                                     "sent_since_last": 2, "auth_429_total": 0,
                                     "connect_ok_total": 27}  # fmt: skip


def test_merging_one_part_returns_it_unchanged():
    part = _part(5, 5, [1.0], 1)
    assert fs.merge([part]) is part
