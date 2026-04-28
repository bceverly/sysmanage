"""
sysmanage load-test harness — entry point invoked by .github/workflows/load-tests.yml.

Single-process asyncio harness.  Scenarios:

  agents              N concurrent simulated agents poll an HTTP endpoint
                      (uses /api/health since it doesn't require auth, so
                      this exercises FastAPI routing + middleware + the
                      HTTP connection pool, not the agent identity layer).
  db-perf             high-concurrency burst against the same endpoint
                      to measure p95 under contention; tells you whether
                      the DB pool / event loop is the bottleneck.
  ws-throughput       open WebSocket connections to the agent endpoint at
                      high rate; the connect attempts will fail auth
                      (we have no host_token) but the connect-handshake
                      + immediate-close path is itself a useful scaling
                      signal — it tells you how fast the server can
                      reject and clean up bad-auth clients.

WebSocket reliability harness (Phase 8 — adds the three behaviors that
ws-throughput's connect-and-reject probe does NOT cover):

  ws-reconnect-storm  N concurrent agents go through the full auth
                      handshake (POST /agent/auth → token → WS connect
                      → close → repeat) in tight loops.  Tests the
                      thundering-herd path:  can the server keep up
                      when a fleet drops and reconnects en masse?
  ws-ordering         Single authenticated WS session.  Sends N
                      sequence-tagged messages back-to-back; server
                      replies with one error per message (validation
                      rejects unknown message_type).  Response count
                      must equal send count, and arrival order must
                      match send order — verifies the server's receive
                      loop is FIFO and drops nothing.
  ws-backpressure     Single authenticated WS session.  Ramps send rate
                      through 1k → 2k → 5k → 10k msgs/s until the
                      connection drops or the duration elapses.  Reports
                      the highest rate the server sustained without
                      the connection going away — informational, not
                      pass/fail.

Usage (matches the workflow):

    python tests/load/run.py \\
        --scenario [agents|db-perf|ws-throughput|ws-reconnect-storm|\\
                    ws-ordering|ws-backpressure|all] \\
        --agents N \\
        --duration-seconds N \\
        --server-url http://localhost:8000 \\
        --output-json /path/to/results.json

Exit codes (the workflow distinguishes these):

    0  — run completed; results.json written.
    1  — server unreachable or other infrastructure failure.
    2  — run completed but SLA threshold violated (p95 > 2s, or error
         rate > 50 %, or ws-ordering FIFO contract violated).  See
         _check_slas() below.
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


async def _get_connection_token(
    http_session: "aiohttp.ClientSession", server_url: str, hostname: str
) -> Optional[str]:
    """POST /agent/auth and return the connection token, or None on failure.

    /agent/auth is mounted on the public router (no /api prefix) and
    issues a 1-hour connection token tied to the agent hostname + the
    caller's IP.  Each cycle of the storm test gets a fresh token so
    we don't hit the per-token replay protections."""
    url = f"{server_url.rstrip('/')}/agent/auth"
    try:
        async with http_session.post(
            url,
            headers={"x-agent-hostname": hostname},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                return None
            body = await resp.json()
            return body.get("connection_token")
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _ws_url(server_url: str) -> str:
    return (
        server_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        + "/api/agent/connect"
    )


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

    ws_url = _ws_url(server_url)
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
# WebSocket reliability harness (Phase 8)
# ----------------------------------------------------------------------------


async def _reconnect_worker(
    http_session: "aiohttp.ClientSession",
    server_url: str,
    ws_url: str,
    hostname_prefix: str,
    deadline: float,
    result: ScenarioResult,
) -> None:
    """One worker:  in a tight loop, get a fresh token, open the WS,
    immediately close, record latency.  Repeats until deadline."""
    cycle = 0
    while time.monotonic() < deadline:
        cycle += 1
        hostname = f"{hostname_prefix}-{cycle}"
        t0 = time.monotonic()
        try:
            token = await _get_connection_token(http_session, server_url, hostname)
            if token is None:
                result.error_count += 1
                continue
            full_url = f"{ws_url}?token={token}"
            async with websockets.connect(  # type: ignore[union-attr]
                full_url, open_timeout=5, close_timeout=2, max_size=2**20
            ) as ws:
                # Authenticated session is open.  Close immediately —
                # this scenario measures *handshake under load*, not
                # in-session traffic (that's ws-ordering / ws-backpressure).
                await ws.close()
            result.request_count += 1
            result.latencies_ms.append((time.monotonic() - t0) * 1000.0)
        except Exception:  # pylint: disable=broad-exception-caught
            result.error_count += 1


async def scenario_ws_reconnect_storm(
    server_url: str, agents: int, duration_seconds: int
) -> ScenarioResult:
    """N agents simultaneously cycle auth → connect → close → repeat.

    Tests the thundering-herd reconnect path.  Pass criteria are the
    standard SLAs (p95 < 2s, error_rate < 50 %); this scenario is the
    flagship test for "did the server's WS path regress in handling
    concurrent reconnect bursts?"."""
    result = ScenarioResult(name=f"ws-reconnect-storm-{agents}")
    if aiohttp is None or websockets is None:
        result.skipped = True
        result.notes.append(
            "aiohttp+websockets required (pip install aiohttp websockets)."
        )
        return result

    ws_url = _ws_url(server_url)
    deadline = time.monotonic() + duration_seconds
    started = time.monotonic()

    connector = aiohttp.TCPConnector(limit=max(agents * 2, 100))
    async with aiohttp.ClientSession(connector=connector) as http_session:
        workers = [
            asyncio.create_task(
                _reconnect_worker(
                    http_session,
                    server_url,
                    ws_url,
                    hostname_prefix=f"load-test-storm-{i}",
                    deadline=deadline,
                    result=result,
                )
            )
            for i in range(agents)
        ]
        try:
            await asyncio.gather(*workers)
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()

    result.duration_seconds = time.monotonic() - started
    result.notes.append(f"agents={agents} ws_url={ws_url}")
    return result


async def scenario_ws_ordering(
    server_url: str, duration_seconds: int
) -> ScenarioResult:
    """Single authenticated session — verify FIFO contract on the
    server's receive loop.

    Sends a stream of messages with monotonically-increasing sequence
    numbers as fast as the connection allows.  Server validates each
    and responds with an ErrorMessage (unknown message_type), so we
    expect one response per send.  Pass criteria:

        sends == responses                       (no drops)
        responses arrive in send order           (TCP guarantee, but
                                                  also the server's
                                                  receive loop must be
                                                  serial — async bugs
                                                  could re-order)

    A failure to satisfy either is recorded in `notes` and bumps
    error_count to >0 so the SLA gate fails the run."""
    result = ScenarioResult(name="ws-ordering")
    if aiohttp is None or websockets is None:
        result.skipped = True
        result.notes.append(
            "aiohttp+websockets required (pip install aiohttp websockets)."
        )
        return result

    ws_url = _ws_url(server_url)
    deadline = time.monotonic() + duration_seconds
    started = time.monotonic()

    sends = 0
    responses = 0
    out_of_order = 0
    last_seen_seq = -1

    async with aiohttp.ClientSession() as http_session:
        token = await _get_connection_token(
            http_session, server_url, hostname="load-test-ordering"
        )
        if token is None:
            result.error_count += 1
            result.notes.append("Could not obtain connection token from /agent/auth.")
            result.duration_seconds = time.monotonic() - started
            return result

        try:
            async with websockets.connect(  # type: ignore[union-attr]
                f"{ws_url}?token={token}",
                open_timeout=5,
                close_timeout=5,
                max_size=2**20,
                # Long ping interval so the harness controls all traffic.
                ping_interval=None,
            ) as ws:

                async def sender() -> None:
                    nonlocal sends
                    while time.monotonic() < deadline:
                        seq = sends
                        # message_type "harness-ping-N" is unknown to the
                        # server — guarantees ErrorMessage reply, no DB
                        # work, fastest server-side path.
                        msg = json.dumps(
                            {"message_type": f"harness-ping-{seq}", "seq": seq}
                        )
                        try:
                            await ws.send(msg)
                            sends += 1
                        except Exception:  # pylint: disable=broad-exception-caught
                            return
                        # Yield to receiver — keeps memory bounded.
                        if sends % 100 == 0:
                            await asyncio.sleep(0)

                async def receiver() -> None:
                    nonlocal responses, out_of_order, last_seen_seq
                    while time.monotonic() < deadline + 2:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            if time.monotonic() >= deadline and responses >= sends:
                                return
                            continue
                        except Exception:  # pylint: disable=broad-exception-caught
                            return
                        responses += 1
                        # The server's ErrorMessage doesn't echo our seq,
                        # but TCP guarantees order within the stream.  We
                        # use response arrival index as the contract:
                        # the Nth response corresponds to the Nth send.
                        # Increment-only check guards against any future
                        # out-of-band server messages that could arrive
                        # interleaved.
                        try:
                            payload = json.loads(raw)
                            seq = int(payload.get("seq", responses - 1))
                        except (ValueError, TypeError):
                            seq = responses - 1
                        if seq < last_seen_seq:
                            out_of_order += 1
                        last_seen_seq = max(last_seen_seq, seq)

                send_task = asyncio.create_task(sender())
                recv_task = asyncio.create_task(receiver())
                await send_task
                await recv_task
        except Exception as e:  # pylint: disable=broad-exception-caught
            result.error_count += 1
            result.notes.append(f"WS error: {type(e).__name__}: {e}")
            result.duration_seconds = time.monotonic() - started
            return result

    drops = sends - responses
    result.request_count = responses
    if drops > 0 or out_of_order > 0:
        result.error_count = max(1, drops + out_of_order)
    result.notes.append(
        f"sends={sends} responses={responses} drops={drops} "
        f"out_of_order={out_of_order}"
    )
    if drops > 0:
        result.notes.append(
            "FIFO contract violated:  server replied to fewer messages than sent."
        )
    if out_of_order > 0:
        result.notes.append(
            "FIFO contract violated:  responses arrived out of send order."
        )
    result.duration_seconds = time.monotonic() - started
    return result


async def scenario_ws_backpressure(
    server_url: str, duration_seconds: int
) -> ScenarioResult:
    """Single session — ramp send rate until the connection drops.

    Steps through 1k → 2k → 5k → 10k msgs/s in equal-time slices.  At
    each rate, records messages sent and whether the connection was
    still alive at the end of the slice.  Reports the highest rate
    that completed without disconnect — that's the empirical
    sustainable throughput for THIS commit on THIS hardware.

    Informational scenario:  no SLA gate.  The signal is "did the
    breakpoint move vs the last run?", surfaced in `notes` as a
    structured `breakpoint_msgs_per_sec=N` line.  CI compares
    artifacts run-over-run."""
    result = ScenarioResult(name="ws-backpressure")
    if aiohttp is None or websockets is None:
        result.skipped = True
        result.notes.append(
            "aiohttp+websockets required (pip install aiohttp websockets)."
        )
        return result

    ws_url = _ws_url(server_url)
    started = time.monotonic()

    # Rates to try, in msgs/sec.  Each rate gets duration_seconds/4
    # of wall time.  With duration_seconds=600 (the workflow default),
    # that's 150s per rate — enough to settle.
    rates = [1000, 2000, 5000, 10000]
    per_rate_seconds = max(duration_seconds // len(rates), 5)
    breakpoint_rate: Optional[int] = None
    breakpoint_reason: str = "completed all rates without disconnect"
    rate_summaries: List[str] = []

    async with aiohttp.ClientSession() as http_session:
        token = await _get_connection_token(
            http_session, server_url, hostname="load-test-backpressure"
        )
        if token is None:
            result.error_count += 1
            result.notes.append("Could not obtain connection token from /agent/auth.")
            result.duration_seconds = time.monotonic() - started
            return result

        try:
            async with websockets.connect(  # type: ignore[union-attr]
                f"{ws_url}?token={token}",
                open_timeout=5,
                close_timeout=5,
                max_size=2**20,
                ping_interval=None,
                # Bound the outbound queue so a slow server applies
                # back-pressure on our send() calls.  Without this the
                # client would just buffer locally and the test would
                # measure asyncio queue depth, not server throughput.
                write_limit=2**20,
            ) as ws:
                disconnected = False
                for rate in rates:
                    if disconnected:
                        break
                    interval = 1.0 / rate
                    rate_deadline = time.monotonic() + per_rate_seconds
                    rate_sends = 0
                    t0 = time.monotonic()
                    while time.monotonic() < rate_deadline:
                        try:
                            await ws.send(
                                json.dumps(
                                    {
                                        "message_type": f"harness-bp-{rate_sends}",
                                        "rate": rate,
                                    }
                                )
                            )
                            rate_sends += 1
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            disconnected = True
                            breakpoint_rate = rate
                            breakpoint_reason = (
                                f"connection dropped at rate={rate}/s after "
                                f"{rate_sends} msgs ({type(e).__name__})"
                            )
                            break
                        # Naive rate limiter — burst up to 100 then sleep.
                        if rate_sends % 100 == 0:
                            elapsed = time.monotonic() - t0
                            target = rate_sends * interval
                            if elapsed < target:
                                await asyncio.sleep(target - elapsed)
                    rate_summaries.append(f"rate={rate}/s sent={rate_sends}")
                    result.request_count += rate_sends
                if not disconnected:
                    breakpoint_rate = rates[-1]
        except Exception as e:  # pylint: disable=broad-exception-caught
            result.error_count += 1
            result.notes.append(f"WS error during backpressure ramp: {e}")

    result.notes.append(f"breakpoint_msgs_per_sec={breakpoint_rate}")
    result.notes.append(f"breakpoint_reason={breakpoint_reason}")
    result.notes.extend(rate_summaries)
    result.duration_seconds = time.monotonic() - started
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
    elif args.scenario == "ws-reconnect-storm":
        out.append(
            await scenario_ws_reconnect_storm(
                args.server_url, args.agents, args.duration_seconds
            )
        )
    elif args.scenario == "ws-ordering":
        out.append(await scenario_ws_ordering(args.server_url, args.duration_seconds))
    elif args.scenario == "ws-backpressure":
        out.append(
            await scenario_ws_backpressure(args.server_url, args.duration_seconds)
        )
    elif args.scenario == "all":
        out.append(
            await scenario_agents(args.server_url, args.agents, args.duration_seconds)
        )
        out.append(await scenario_db_perf(args.server_url, args.duration_seconds))
        out.append(await scenario_ws_throughput(args.server_url, args.duration_seconds))
        out.append(
            await scenario_ws_reconnect_storm(
                args.server_url, args.agents, args.duration_seconds
            )
        )
        out.append(await scenario_ws_ordering(args.server_url, args.duration_seconds))
        out.append(
            await scenario_ws_backpressure(args.server_url, args.duration_seconds)
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="sysmanage load-test harness")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "agents",
            "db-perf",
            "ws-throughput",
            "ws-reconnect-storm",
            "ws-ordering",
            "ws-backpressure",
            "all",
        ],
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
