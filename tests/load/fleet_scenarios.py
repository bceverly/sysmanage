# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet scenarios for the Phase 22 scale harness.

  fleet-steady         N agents, started spread over one collection cycle
                       (the kindest start today's code can get), run for
                       --duration-seconds.
  fleet-restart-storm  the same, then the server is restarted after
                       --warmup-seconds: every agent reconnects at once.
  fleet-agent-restart  the same, but every AGENT restarts after
                       --warmup-seconds (a fleet-wide upgrade): each
                       registers again and reconnects.  The agent keeps its
                       send-on-change memory on disk (22.2) unless
                       --forget-on-restart, the agent before it.

Both enroll the fleet first: every agent registers through the real
endpoint, then the hosts are approved with one UPDATE in the harness's OWN
database (approval's certificate is only used for mutual TLS, which this
plain-ws harness never does).  The server is the disposable one from
tests/load/stack.py -- a restart needs a server the harness owns.

The verdict is the Phase 22 exit criteria, measured: nothing expires, no
agent is locked out or demoted to polling, the inbound backlog drains, the
fleet reconnects, no host is marked down by the outage, and the load is flat.
On today's code these are EXPECTED to fail -- that is the baseline.  With
--report-only the run still exits 0 so a baseline can be recorded.
"""

import asyncio
import json
import shlex
import statistics
import subprocess  # nosec B404 - fixed argv lists to ssh/scp
import time
from collections import Counter
from types import SimpleNamespace
from typing import List, Optional

from sqlalchemy import create_engine, text

from tests.load import fleet_shards
from tests.load import stack
from tests.load.fleet import COLLECTION_S, Fleet
from tests.load.observe import Observer

APPROVE_SQL = text(
    "UPDATE host SET approval_status = 'approved' "
    "WHERE fqdn LIKE '%.sim.test' AND approval_status = 'pending'"
)


def _tenant_db_urls(state) -> list:
    return [t["db_url"] for t in state.get("tenants") or []]


def _tokens(state) -> list:
    return [t["token"] for t in state.get("tenants") or []]


def _approve_all(state) -> int:
    """Approve the fleet in the main database and every tenant database."""
    return sum(_approve(url) for url in [state["db_url"], *_tenant_db_urls(state)])


def _approve(db_url: str) -> int:
    engine = create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            return conn.execute(APPROVE_SQL).rowcount
    finally:
        engine.dispose()


def _pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(int(len(ordered) * p), len(ordered) - 1)], 1)


def _series(samples, key):
    return [s[key] for s in samples if s.get(key) is not None]


def _queue_total(sample, suffix):
    return sum(v for k, v in sample.get("queue", {}).items() if k.endswith(suffix))


def _reconnect_seconds(timeline, restart_t, agents, fraction=0.95):
    """Seconds after the restart until ``fraction`` of the fleet is connected
    AGAIN -- after the drop.  The first samples after the restart command
    still count the old connections (the agents have not noticed the server
    going yet), which read as a 0.1 s "reconnect" and shrank the restart
    window the spike ratio leaves out (seen 2026-10-02 once shutdown ran to
    completion and the sockets closed a little later)."""
    if restart_t is None:
        return None
    threshold = fraction * agents
    dropped = False
    for row in timeline:
        if row["t"] <= restart_t:
            continue
        if not dropped:
            dropped = row["connected"] < threshold
            continue
        if row["connected"] >= threshold:
            return round(row["t"] - restart_t, 1)
    return None


def _spike_ratio(timeline, after_t, restart_window=None):
    """Busiest window's send count over the average: 1.0 is perfectly flat.

    STEADY state only: windows inside ``restart_window`` (the restart until
    the fleet is back, plus a minute) are left out.  The reconnect after an
    outage is a one-off, bounded event -- and with send-on-change the steady
    average is small, so counting it would read the transient as a 5-minute
    spike, which is what this measures.  The transient is still reported:
    see ``reconnect_95pct_seconds`` and the timeline."""
    lo, hi = restart_window or (None, None)
    sends = [
        row["sent_since_last"]
        for row in timeline
        if row["t"] > after_t and not (lo is not None and lo <= row["t"] <= hi)
    ]
    if len(sends) < 3 or not sum(sends):
        return None
    return round(max(sends) / statistics.mean(sends), 2)


def _restart_window(timeline, restart_t, agents):
    """``(start, end)`` of the reconnect transient, or None without a restart."""
    if restart_t is None:
        return None
    back = _reconnect_seconds(timeline, restart_t, agents)
    return restart_t, restart_t + (back if back is not None else 300) + 60


def _summarize(name, fleet, observer, restart_t, warmup):
    stats = fleet.stats
    samples = [s for s in observer.samples if "event" not in s]
    agents = len(fleet.agents)
    after = [s for s in samples if restart_t is not None and s["t"] > restart_t]
    final = samples[-1] if samples else {}
    hosts_down = [s.get("hosts", {}).get("approved.down", 0) for s in after]
    summary = {
        "name": name,
        "agents": agents,
        "source_ips": fleet.source_ips,
        "time_scale": fleet.time_scale,
        "connected_at_end": stats.connected_at_end,
        "reconnect_95pct_seconds": _reconnect_seconds(stats.timeline, restart_t, agents),
        "auth_429": stats.counts["auth_429"],
        "fallback_to_polling": stats.counts["fallback_to_polling"],
        "register_gave_up": stats.counts["register_gave_up"],
        "errors_received": dict(stats.errors_received),
        "messages_sent": sum(stats.sent.values()),
        "megabytes_sent": round(stats.bytes_sent / 1e6, 1),
        "heartbeat_rtt_p50_ms": _pct(stats.heartbeat_rtt_ms, 0.50),
        "heartbeat_rtt_p95_ms": _pct(stats.heartbeat_rtt_ms, 0.95),
        "heartbeat_rtt_max_ms": _pct(stats.heartbeat_rtt_ms, 1.0),
        "messages_sent_after_restart": sum(row["sent_since_last"] for row in stats.timeline
                                           if restart_t is not None and row["t"] > restart_t),
        "report_window_p50_s": _pct(getattr(stats, "report_windows", []), 0.50),
        "report_window_max_s": _pct(getattr(stats, "report_windows", []), 1.0),
        "health_p95_ms": _pct(_series(samples, "health_ms"), 0.95),
        "health_max_ms": _pct(_series(samples, "health_ms"), 1.0),
        "health_failures": sum(1 for s in samples if s.get("health_ms") is None),
        "server_cpu_mean_percent": round(statistics.mean(_series(samples, "server_cpu_percent")), 1)
        if _series(samples, "server_cpu_percent") else None,
        "server_rss_max_mb": max(_series(samples, "server_rss_mb"), default=None),
        "inbound_pending_max": max((_queue_total(s, "inbound.pending") for s in samples), default=0),
        "inbound_pending_final": _queue_total(final, "inbound.pending"),
        "oldest_inbound_pending_max_s": max(_series(samples, "oldest_inbound_pending_s"), default=None),
        "expired_rows_final": _queue_total(final, ".expired"),
        "hosts_marked_down_max_after_restart": max(hosts_down, default=0),
        "pg_connections_max": max(_series(samples, "pg_connections"), default=None),
        "host_load_per_cpu_p90": _pct(_series(samples, "host_load_per_cpu"), 0.90),
        # CPU used by processes outside the run, per CPU: see verdict().
        "other_cpu_per_cpu_p90": _pct(_series(samples, "other_cpu_per_cpu"), 0.90),
        "send_spike_ratio": _spike_ratio(
            stats.timeline, warmup, _restart_window(stats.timeline, restart_t, agents)
        ),
        "agent_counts": dict(stats.counts),
        "sent_by_type": dict(stats.sent),
    }  # fmt: skip
    return summary


# Share of the machine's CPU used by processes OUTSIDE the run (server,
# PostgreSQL, container plumbing, OpenBAO and the harness are the run) above
# which the run measured a shared machine: 2026-10-04 a run on a workstation
# shared with a browser, chat clients and another project's tests looked three
# times worse than the code was.  Measured from per-process CPU time, not load
# average, which cannot tell a busy server on a small box from a shared one.
OTHER_CPU_LIMIT = 0.25


def verdict(summary) -> List[str]:
    """The Phase 22 exit criteria, as violations of today's run."""
    out = []
    other = summary.get("other_cpu_per_cpu_p90")
    if other is not None and other > OTHER_CPU_LIMIT:
        out.append(
            f"RUN NOT TRUSTWORTHY: processes outside the run used {other:.0%} of "
            f"the server machine's CPU (p90, limit {OTHER_CPU_LIMIT:.0%}); rerun "
            "on a quiet machine before reading the numbers"
        )
    if summary["expired_rows_final"]:
        out.append(
            f"{summary['expired_rows_final']} queued messages EXPIRED (silent data loss)"
        )
    if summary["auth_429"]:
        out.append(
            f"{summary['auth_429']} connection attempts refused with 429 (agents locked out)"
        )
    if summary["fallback_to_polling"]:
        out.append(f"{summary['fallback_to_polling']} agents demoted to HTTP polling")
    if summary["register_gave_up"]:
        out.append(f"{summary['register_gave_up']} agents gave up registering")
    if summary["connected_at_end"] < 0.99 * summary["agents"]:
        out.append(
            f"only {summary['connected_at_end']}/{summary['agents']} agents connected at the end"
        )
    final, peak = summary["inbound_pending_final"], summary["inbound_pending_max"]
    if peak and final > max(0.05 * peak, summary["agents"]):
        out.append(
            f"inbound backlog did not drain: {final} pending at the end (peak {peak})"
        )
    if summary["hosts_marked_down_max_after_restart"]:
        out.append(
            f"{summary['hosts_marked_down_max_after_restart']} hosts marked DOWN by the outage"
        )
    spike = summary["send_spike_ratio"]
    if spike is not None and spike > 2.0:
        out.append(f"agent traffic is bursty: busiest window {spike}x the average")
    return out


async def _timeline(fleet, started, interval):
    while True:
        await asyncio.sleep(interval)
        fleet.stats.snapshot(time.monotonic() - started)


async def run_fleet(args) -> dict:
    """Run one fleet scenario against the stack; returns the report."""
    if not args.reuse_stack:
        print("resetting the load stack (empty database) ...")
        await asyncio.to_thread(stack.reset)
    state = stack.load_state()
    base = f"http://127.0.0.1:{state['port']}"
    fleet = Fleet(
        base,
        args.agents,
        args.source_ips,
        args.time_scale,
        args.packages,
        send_on_change=args.send_on_change,
        jitter=args.jitter,
        identity_auth=getattr(args, "identity_auth", False),
        report_window=getattr(args, "report_window", False),
        enrollment_tokens=_tokens(state),
    )
    print(
        f"enrolling {args.agents} agents from {fleet.source_ips} source address(es) ..."
    )
    t0 = time.monotonic()
    await fleet.register_all()
    approved = await asyncio.to_thread(_approve_all, state)
    print(f"  registered {fleet.stats.counts['register_ok']}, approved {approved} "
          f"in {time.monotonic() - t0:.0f}s")  # fmt: skip

    observer = Observer(base, state["db_url"], lambda: stack.load_state().get("server_pid"),
                        interval=args.sample_seconds,
                        tenant_db_urls=_tenant_db_urls(state))  # fmt: skip
    started = time.monotonic()
    observer.start()
    ticker = asyncio.create_task(_timeline(fleet, started, args.sample_seconds))
    # Spread the starts over one (scaled) collection cycle: the kindest
    # start today's code can get, so the restart's damage stands out.
    fleet.start(ramp_seconds=COLLECTION_S / args.time_scale)
    restart_t = None
    try:
        if args.scenario == "fleet-restart-storm":
            await asyncio.sleep(args.warmup_seconds)
            restart_t = round(time.monotonic() - started, 1)
            observer.mark("server restart")
            print(
                f"  t={restart_t}s: restarting the server (down {args.down_seconds}s) ..."
            )
            await asyncio.to_thread(
                stack.restart_server, stack.load_state(), args.down_seconds
            )
            await asyncio.sleep(args.duration_seconds)
        elif args.scenario == "fleet-agent-restart":
            await asyncio.sleep(args.warmup_seconds)
            restart_t = round(time.monotonic() - started, 1)
            observer.mark("agent restart")
            print(f"  t={restart_t}s: restarting every agent ...")
            await fleet.restart_agents(forget=getattr(args, "forget_on_restart", False))
            await asyncio.sleep(args.duration_seconds)
        else:
            await asyncio.sleep(args.warmup_seconds + args.duration_seconds)
    finally:
        ticker.cancel()
        # Before stop() disconnects everyone.
        fleet.stats.connected_at_end = fleet.stats.connected
        await fleet.stop()
        await observer.stop()
    summary = _summarize(f"{args.scenario}-{args.agents}", fleet, observer, restart_t,
                         args.warmup_seconds)  # fmt: skip
    return {
        "scenario": args.scenario,
        # compare.py matches run-over-run by scenario name under "scenarios".
        "scenarios": [summary],
        "summary": summary,
        "violations": verdict(summary),
        "server_samples": observer.samples,
        "pg_top_statements": observer.top_statements,
        "agent_timeline": fleet.stats.timeline,
    }


# -- the fleet on another machine ------------------------------------------------

_REMOTE_DIR = "sysmanage-loadsim"
_SHIPPED = ("tests/__init__.py", "tests/load/__init__.py", "tests/load/fleet.py",
            "tests/load/payloads.py", "tests/load/fleet_remote.py")  # fmt: skip


def _ship_code(host: str) -> None:
    """Copy the simulator to ``host:~/sysmanage-loadsim/code`` (a venv with
    aiohttp + websockets is expected at ``~/sysmanage-loadsim/venv``)."""
    root = stack.REPO
    subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                    f"mkdir -p {_REMOTE_DIR}/code/tests/load"], check=True)  # fmt: skip
    for rel in _SHIPPED:
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", str(root / rel),
                        f"{host}:{_REMOTE_DIR}/code/{rel}"], check=True)  # fmt: skip


def _remote_fleet(stats: dict) -> SimpleNamespace:
    """The remote fleet's report, shaped like a local Fleet for _summarize."""
    fleet_stats = SimpleNamespace(
        counts=Counter(stats["counts"]), sent=Counter(stats["sent"]),
        errors_received=Counter(stats["errors_received"]),
        heartbeat_rtt_ms=stats["heartbeat_rtt_ms"],
        report_windows=stats.get("report_windows", []),
        connected_at_end=stats["connected_at_end"], bytes_sent=stats["bytes_sent"],
        timeline=stats["timeline"],
    )  # fmt: skip
    return SimpleNamespace(stats=fleet_stats, agents=range(stats["agents"]),
                           source_ips=stats["source_ips"], time_scale=stats["time_scale"])  # fmt: skip


async def _expect(stream, prefix: str) -> str:
    while True:
        line = (await stream.readline()).decode("utf-8", "replace")
        if not line:
            raise SystemExit(f"the remote fleet ended before {prefix!r}")
        if line.startswith(prefix):
            return line[len(prefix) :].strip()


async def _start_shard(args, state, shard, run_seconds):
    """One simulator process on ``shard.host`` over ssh."""
    flags = [f for f, on in (("--send-on-change", args.send_on_change),
                             ("--jitter", args.jitter),
                             ("--identity-auth", getattr(args, "identity_auth", False)),
                             ("--report-window", getattr(args, "report_window", False))) if on]  # fmt: skip
    inner = " ".join(
        # Every agent holds a socket: raise the soft file limit to the hard
        # one (1024 by default on Ubuntu).  sh -c: the login shell may be csh.
        ["ulimit -n $(ulimit -Hn) 2>/dev/null;",
         f"cd {_REMOTE_DIR}/code &&", "exec ../venv/bin/python -m tests.load.fleet_remote",
         f"--base http://{args.server_address}:{state['port']}",
         f"--agents {shard.count}", f"--first-index {shard.first}",
         f"--run-seconds {run_seconds}",
         f"--time-scale {args.time_scale}", f"--packages {args.packages}",
         f"--sample-seconds {args.sample_seconds}", *flags,
         *([f"--enrollment-tokens {','.join(_tokens(state))}"] if _tokens(state) else [])]
    )  # fmt: skip
    remote_cmd = "sh -c " + shlex.quote(inner)
    # Closed by the caller; the subprocess writes to it throughout.
    log = open(  # pylint: disable=consider-using-with
        stack.STATE_DIR / f"remote-fleet-{shard.host}-{shard.first}.log", "wb"
    )
    proc = await asyncio.create_subprocess_exec(
        "ssh", "-o", "BatchMode=yes", shard.host, remote_cmd,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=log,
        limit=256 * 1024 * 1024,  # the STATS line is large (default: 64 KB)
    )  # fmt: skip
    return proc, log


async def _tell_all(procs, line: bytes):
    for proc in procs:
        proc.stdin.write(line)
        await proc.stdin.drain()


async def run_remote_fleet(args) -> dict:  # pylint: disable=too-many-locals
    """Like run_fleet, with the agents on other machines over ssh:
    ``--remote-fleet HOST`` or shards ``HOST:PROCS,HOST:PROCS`` (fleet_shards)."""
    if not args.reuse_stack:
        print("resetting the load stack (empty database) ...")
        await asyncio.to_thread(stack.reset)
    state = stack.load_state()
    shards = fleet_shards.split(args.remote_fleet, args.agents)
    for host in sorted({s.host for s in shards}):
        await asyncio.to_thread(_ship_code, host)
    storm = args.scenario == "fleet-restart-storm"
    run_seconds = args.warmup_seconds + (
        args.down_seconds + args.duration_seconds if storm else args.duration_seconds
    )
    started_shards = [await _start_shard(args, state, s, run_seconds) for s in shards]
    procs = [proc for proc, _log in started_shards]
    print(f"enrolling {args.agents} agents on {args.remote_fleet} "
          f"({len(shards)} process(es)) ...", flush=True)  # fmt: skip
    registered = sum(
        int(n)
        for n in await asyncio.gather(
            *(_expect(p.stdout, "REGISTERED ") for p in procs)
        )
    )
    approved = await asyncio.to_thread(_approve_all, state)
    print(f"  registered {registered}, approved {approved}", flush=True)
    observer = Observer(f"http://127.0.0.1:{state['port']}", state["db_url"],
                        lambda: stack.load_state().get("server_pid"),
                        interval=args.sample_seconds,
                        tenant_db_urls=_tenant_db_urls(state))  # fmt: skip
    await _tell_all(procs, b"GO\n")
    started = time.monotonic()
    observer.start()
    restart_t = None
    try:
        if storm:
            await asyncio.sleep(args.warmup_seconds)
            restart_t = round(time.monotonic() - started, 1)
            observer.mark("server restart")
            print(
                f"  t={restart_t}s: restarting the server (down {args.down_seconds}s) ..."
            )
            await asyncio.to_thread(
                stack.restart_server, stack.load_state(), args.down_seconds
            )
        elif args.scenario == "fleet-agent-restart":
            await asyncio.sleep(args.warmup_seconds)
            restart_t = round(time.monotonic() - started, 1)
            observer.mark("agent restart")
            print(f"  t={restart_t}s: restarting every agent ...", flush=True)
            forget = getattr(args, "forget_on_restart", False)
            await _tell_all(procs, b"RESTART forget\n" if forget else b"RESTART\n")
            await asyncio.gather(*(_expect(p.stdout, "RESTARTED") for p in procs))
        parts = await asyncio.gather(*(_expect(p.stdout, "STATS ") for p in procs))
        stats = fleet_shards.merge([json.loads(part) for part in parts])
    finally:
        await observer.stop()
        for proc, log in started_shards:
            await proc.wait()
            log.close()
    # Each machine is one source address (bind_source=False on remote fleets).
    stats["source_ips"] = len({s.host for s in shards})
    fleet = _remote_fleet(stats)
    summary = _summarize(f"{args.scenario}-{args.agents}", fleet, observer, restart_t,
                         args.warmup_seconds)  # fmt: skip
    summary["remote_fleet"] = args.remote_fleet
    return {"scenario": args.scenario, "scenarios": [summary], "summary": summary,
            "violations": verdict(summary), "server_samples": observer.samples,
            "pg_top_statements": observer.top_statements,
            "agent_timeline": fleet.stats.timeline}  # fmt: skip


def main_fleet(args) -> int:
    """Entry point from run.py for the fleet-* scenarios."""
    runner = run_remote_fleet if getattr(args, "remote_fleet", None) else run_fleet
    if args.scenario == "fleet-wave-push":
        from tests.load.wave_scenarios import (  # pylint: disable=import-outside-toplevel
            run_wave,
        )

        runner = run_wave
    report = asyncio.run(runner(args))
    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(json.dumps(report["summary"], indent=2, default=str))
    if report["violations"]:
        print("\nPhase 22 criteria NOT met:")
        for line in report["violations"]:
            print(f"  - {line}")
        return 0 if args.report_only else 2
    print("\nPhase 22 criteria met.")
    return 0
