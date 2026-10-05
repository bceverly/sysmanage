# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A remote fleet split across processes and machines (Phase 22 harness).

One simulator process is one Python thread: ~10,000 agents was about a core,
and one machine's address holds at most ~55,000 connections to one server
port.  For 20,000 agents and up the fleet runs as SHARDS -- several processes
on several machines, each with its own range of agent numbers -- and the
controller merges what they report:

    --remote-fleet t14:4,freebsd:3,t480:2    (host:processes, comma-separated)
"""

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List

TIMELINE_SUMS = ("connected", "polling", "sent_since_last", "auth_429_total",
                 "connect_ok_total")  # fmt: skip


@dataclass(frozen=True)
class Shard:
    """One simulator process: ``count`` agents numbered from ``first``."""

    host: str
    first: int
    count: int


def parse(spec: str) -> List[str]:
    """``"a:2,b"`` -> ``["a", "a", "b"]``: one entry per process."""
    hosts = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        host, _, procs = part.partition(":")
        n = int(procs) if procs else 1
        if n < 1 or not host:
            raise ValueError(f"bad --remote-fleet entry {part!r}")
        hosts.extend([host] * n)
    if not hosts:
        raise ValueError("--remote-fleet names no host")
    return hosts


def split(spec: str, agents: int) -> List[Shard]:
    """Spread ``agents`` evenly over the processes ``spec`` names."""
    hosts = parse(spec)
    base, extra = divmod(agents, len(hosts))
    shards, first = [], 0
    for i, host in enumerate(hosts):
        count = base + (1 if i < extra else 0)
        if count:
            shards.append(Shard(host, first, count))
        first += count
    return shards


def merge(parts: List[Dict]) -> Dict:
    """One report from the shards' ``STATS``: sums, concatenated samples, and
    the timelines added row by row (the shards start on the same GO and
    sample at the same interval; the shortest timeline bounds the merge)."""
    if len(parts) == 1:
        return parts[0]
    out = {
        "agents": sum(p["agents"] for p in parts),
        "time_scale": parts[0]["time_scale"],
        "connected_at_end": sum(p["connected_at_end"] for p in parts),
        "bytes_sent": sum(p["bytes_sent"] for p in parts),
        "heartbeat_rtt_ms": [v for p in parts for v in p["heartbeat_rtt_ms"]],
        "report_windows": [v for p in parts for v in p.get("report_windows", [])],
    }
    for key in ("counts", "sent", "errors_received"):
        total = Counter()
        for p in parts:
            total.update(p[key])
        out[key] = dict(total)
    rows = min(len(p["timeline"]) for p in parts)
    out["timeline"] = [
        {"t": parts[0]["timeline"][i]["t"],
         **{k: sum(p["timeline"][i].get(k, 0) for p in parts) for k in TIMELINE_SUMS}}
        for i in range(rows)
    ]  # fmt: skip
    return out
