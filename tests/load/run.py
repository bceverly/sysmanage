"""
sysmanage load-test harness — entry point invoked by .github/workflows/load-tests.yml.

Single-process asyncio harness.  Three scenarios:

  agents          N concurrent simulated agents poll an HTTP endpoint
                  (uses /api/health since it doesn't require auth, so
                  this exercises FastAPI routing + middleware + the
                  HTTP connection pool, not the agent identity layer).
  db-perf         high-concurrency burst against the same endpoint
                  to measure p95 under contention; tells you whether
                  the DB pool / event loop is the bottleneck.
  ws-throughput   open WebSocket connections to the agent endpoint at
                  high rate; the connect attempts will fail auth
                  (we have no host_token) but the connect-handshake
                  + immediate-close path is itself a useful scaling
                  signal — it tells you how fast the server can
                  reject and clean up bad-auth clients.

Usage (matches the workflow):

    python tests/load/run.py \\
        --scenario [agents|db-perf|ws-throughput|all] \\
        --agents N \\
        --duration-seconds N \\
        --server-url http://localhost:8000 \\
        --output-json /path/to/results.json

Exit codes (the workflow distinguishes these):

    0  — run completed; results.json written.
    1  — server unreachable or other infrastructure failure.
    2  — run completed but SLA threshold violated (p95 > 2s, or error
         rate > 50 %).  See _check_slas() below.
    5  — scenario not implemented (workflow treats this as a soft skip).

Caveats documented in the workflow comment block:  results from this
harness are not representative of production hardware — server and
"agents" run on the same 4-vCPU GitHub-hosted runner over loopback.
Numbers are good for catching regressions, not capacity planning.
"""

# pylint: disable=missing-function-docstring,missing-class-docstring

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import List, Optional

try:
    import aiohttp  # type: ignore
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

try:
    import websockets  # type: ignore
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]


# SLA thresholds.  Anything stricter goes here — the workflow only
# cares about exit code 2 vs 0, so fold all SLA logic into one place.
SLA_P95_MS = 2000.0
SLA_ERROR_RATE = 0.50


@dataclass
class ScenarioResult:
    name: str
    duration_seconds: float = 0.0
    request_count: int = 0
    error_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    skipped: bool = False

    def percentile(self, p: float) -> Optional[float]:
        if not self.latencies_ms:
            return None
        sorted_lat = sorted(self.latencies_ms)
        idx = min(int(len(sorted_lat) * p), len(sorted_lat) - 1)
        return sorted_lat[idx]

    def summary(self) -> dict:
        total = self.request_count + self.error_count
        return {
            "name": self.name,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 2),
            "requests_ok": self.request_count,
            "requests_error": self.error_count,
            "p50_ms": (
                round(self.percentile(0.50), 2)
                if self.percentile(0.50) is not None
                else None
            ),
            "p95_ms": (
                round(self.percentile(0.95), 2)
                if self.percentile(0.95) is not None
                else None
            ),
            "p99_ms": (
                round(self.percentile(0.99), 2)
                if self.percentile(0.99) is not None
                else None
            ),
            "throughput_rps": (
                round(
                    (self.request_count + self.error_count) / self.duration_seconds, 2
                )
                if self.duration_seconds > 0
                else 0.0
            ),
            "error_rate": round(self.error_count / total, 4) if total > 0 else 0.0,
            "notes": self.notes,
        }


# ----------------------------------------------------------------------------
# HTTP scenarios
# ----------------------------------------------------------------------------


async def _http_worker(
    session: "aiohttp.ClientSession",
    url: str,
    deadline: float,
    result: ScenarioResult,
    interval_seconds: float,
) -> None:
    """One worker hits `url` until `deadline`; appends timings/errors to `result`."""
    timeout = aiohttp.ClientTimeout(total=10)
    # asyncio.CancelledError inherits from BaseException (Py 3.8+), so the
    # broad `except Exception` below intentionally does not swallow it —
    # cancellation propagates out cleanly when the gather is torn down.
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        try:
            async with session.get(url, timeout=timeout) as resp:
                await resp.read()
                if 200 <= resp.status < 400:
                    result.request_count += 1
                    result.latencies_ms.append((time.monotonic() - t0) * 1000.0)
                else:
                    result.error_count += 1
        except Exception:  # pylint: disable=broad-exception-caught
            result.error_count += 1
        if interval_seconds > 0:
            await asyncio.sleep(interval_seconds)


async def scenario_agents(
    server_url: str, agents: int, duration_seconds: int
) -> ScenarioResult:
    """N concurrent agents — each one polls /api/health every second."""
    result = ScenarioResult(name=f"agents-{agents}")
    if aiohttp is None:
        result.skipped = True
        result.notes.append("aiohttp not installed; skipping (pip install aiohttp).")
        return result

    url = f"{server_url.rstrip('/')}/api/health"
    deadline = time.monotonic() + duration_seconds
    started = time.monotonic()

    connector = aiohttp.TCPConnector(limit=max(agents * 2, 100))
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [
            asyncio.create_task(
                _http_worker(session, url, deadline, result, interval_seconds=1.0)
            )
            for _ in range(agents)
        ]
        try:
            await asyncio.gather(*workers)
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()

    result.duration_seconds = time.monotonic() - started
    return result


async def scenario_db_perf(server_url: str, duration_seconds: int) -> ScenarioResult:
    """Burst-load /api/health to measure p95 under contention.

    Heuristic for DB-pool saturation:  if p95 grows non-linearly with
    concurrency between this scenario and the agents scenario, the
    server's DB pool or event-loop scheduling is the constraint.
    """
    result = ScenarioResult(name="db-perf")
    if aiohttp is None:
        result.skipped = True
        result.notes.append("aiohttp not installed; skipping (pip install aiohttp).")
        return result

    url = f"{server_url.rstrip('/')}/api/health"
    deadline = time.monotonic() + duration_seconds
    started = time.monotonic()

    workers_n = 50
    connector = aiohttp.TCPConnector(limit=workers_n * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [
            asyncio.create_task(
                _http_worker(session, url, deadline, result, interval_seconds=0.05)
            )
            for _ in range(workers_n)
        ]
        try:
            await asyncio.gather(*workers)
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()

    result.duration_seconds = time.monotonic() - started
    result.notes.append(f"workers={workers_n} interval=50ms")
    return result


# ----------------------------------------------------------------------------
# WebSocket scenario
# ----------------------------------------------------------------------------


async def _ws_connect_once(ws_url: str, result: ScenarioResult) -> None:
    """One connect-attempt cycle:  open, send hello, read or close."""
    t0 = time.monotonic()
    try:
        # open_timeout small to bound how long a hung server can stall us;
        # close_timeout small for the same reason on teardown.
        async with websockets.connect(  # type: ignore[union-attr]
            ws_url, open_timeout=5, close_timeout=2, max_size=2**20
        ) as ws:
            try:
                await asyncio.wait_for(ws.send('{"message_type": "ping"}'), timeout=2)
                # Server may reply with auth-required or close — either way
                # we count the round-trip.  Don't fail on the recv side.
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except (
                    asyncio.TimeoutError,
                    Exception,
                ):  # pylint: disable=broad-exception-caught
                    pass
            except (
                asyncio.TimeoutError,
                Exception,
            ):  # pylint: disable=broad-exception-caught
                pass
        result.request_count += 1
        result.latencies_ms.append((time.monotonic() - t0) * 1000.0)
    except Exception:  # pylint: disable=broad-exception-caught
        # Server-side reject = fast-fail = useful data point.  Count as
        # an error so the error_rate signal is preserved.  CancelledError
        # is a BaseException and will not be caught here.
        result.error_count += 1


async def scenario_ws_throughput(
    server_url: str, duration_seconds: int
) -> ScenarioResult:
    """Repeatedly connect to the agent WS endpoint at high rate."""
    result = ScenarioResult(name="ws-throughput")
    if websockets is None:
        result.skipped = True
        result.notes.append(
            "websockets not installed; skipping (pip install websockets)."
        )
        return result

    ws_url = (
        server_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        + "/api/agent/connect"
    )
    deadline = time.monotonic() + duration_seconds
    started = time.monotonic()

    # Sequential connect loop with a small inter-connect pause.  Real
    # parallelism would just OOM on a 16 GB runner past a few hundred
    # concurrent WS contexts — see audit doc.
    while time.monotonic() < deadline:
        await _ws_connect_once(ws_url, result)
        await asyncio.sleep(0.05)

    result.duration_seconds = time.monotonic() - started
    result.notes.append(f"ws_url={ws_url}")
    return result


# ----------------------------------------------------------------------------
# Driver / main
# ----------------------------------------------------------------------------


def _ping_server(server_url: str) -> bool:
    """One synchronous probe — fail fast if the server isn't reachable.

    Returns True on success, False on any error.
    """
    try:
        with urllib.request.urlopen(  # nosec B310 — fixed test URL, not user input
            f"{server_url.rstrip('/')}/api/health", timeout=5
        ) as resp:
            return resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _check_slas(results: List[ScenarioResult]) -> List[str]:
    violations: List[str] = []
    for r in results:
        s = r.summary()
        if s.get("p95_ms") is not None and s["p95_ms"] > SLA_P95_MS:
            violations.append(
                f"{s['name']}: p95={s['p95_ms']:.1f}ms exceeds threshold {SLA_P95_MS:.0f}ms"
            )
        if s.get("error_rate", 0.0) > SLA_ERROR_RATE:
            violations.append(
                f"{s['name']}: error_rate={s['error_rate']:.1%} exceeds threshold "
                f"{SLA_ERROR_RATE:.0%}"
            )
    return violations


async def _dispatch(args: argparse.Namespace) -> List[ScenarioResult]:
    out: List[ScenarioResult] = []
    if args.scenario == "agents":
        out.append(
            await scenario_agents(args.server_url, args.agents, args.duration_seconds)
        )
    elif args.scenario == "db-perf":
        out.append(await scenario_db_perf(args.server_url, args.duration_seconds))
    elif args.scenario == "ws-throughput":
        out.append(await scenario_ws_throughput(args.server_url, args.duration_seconds))
    elif args.scenario == "all":
        out.append(
            await scenario_agents(args.server_url, args.agents, args.duration_seconds)
        )
        out.append(await scenario_db_perf(args.server_url, args.duration_seconds))
        out.append(await scenario_ws_throughput(args.server_url, args.duration_seconds))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="sysmanage load-test harness")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["agents", "db-perf", "ws-throughput", "all"],
    )
    parser.add_argument("--agents", type=int, default=100)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--server-url", default="http://localhost:8000")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    if args.duration_seconds <= 0:
        print("ERROR: --duration-seconds must be > 0", file=sys.stderr)
        return 1

    if not _ping_server(args.server_url):
        print(
            f"ERROR: server at {args.server_url} did not respond to /api/health",
            file=sys.stderr,
        )
        return 1

    results = asyncio.run(_dispatch(args))

    report = {
        "server_url": args.server_url,
        "scenario": args.scenario,
        "duration_seconds_requested": args.duration_seconds,
        "scenarios": [r.summary() for r in results],
    }
    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    # Also stream a summary to stdout so the CI log shows the result
    # without forcing the user to download the artifact.
    print(json.dumps(report, indent=2))

    violations = _check_slas(results)
    if violations:
        print("\nSLA violations:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
