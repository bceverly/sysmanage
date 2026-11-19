# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A fleet-wide command, every host at once (Phase 27, event-loop sweep S5).

Production stalled 30 s on 2026-11-18 when every host was asked to upgrade
its agent at once: the handler was ``async def`` but only made blocking
database calls, so waiting for a connection from a tenant pool of 2 + 6 (two
per request) waited ON the event loop -- nothing else ran, including the work
that would have returned a connection -- and the request failed with
"QueuePool limit of size 2 overflow 6 reached".  Every route handler is now
plain ``def`` (FastAPI's thread pool) or awaits only what is truly async.

This scenario repeats the incident on the disposable multi-tenant stack, on
the DEFAULT pools: after the fleet settles, the console's "upgrade every
agent" is replayed -- one ``POST /api/v1/host/update-agent/{id}`` per host,
``--burst-concurrency`` at a time -- while ``/api/health`` is probed every
200 ms.  Criteria: every request answers 2xx; every host's command is queued;
no pool timeout in the server log; and the server stays responsive (health
p99 under ``HEALTH_P99_LIMIT``, never over ``HEALTH_MAX_LIMIT``).
"""

import asyncio
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional

import aiohttp
from sqlalchemy import create_engine, text

from tests.load import stack, stack_mt

HEALTH_P99_LIMIT = 1.0  # seconds
HEALTH_MAX_LIMIT = 5.0
PROBE_SECONDS = 0.2

_MINT = r"""
import json, sys
from backend.auth.auth_handler import sign_jwt
user, tenants = sys.argv[1], json.loads(sys.argv[2])
out = {}
for tenant in tenants:
    token = sign_jwt(user, tenant)
    out[tenant] = token.get("Authorization") if isinstance(token, dict) else token
print(json.dumps(out))
"""


def _engine(db_url: str):
    """The harness's databases speak psycopg 3 (a bare postgresql:// URL
    would make SQLAlchemy reach for psycopg2, which is not installed)."""
    return create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))


def _pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 3)


def mint_tokens(state) -> Dict[str, str]:
    """One admin JWT per tenant (the ``tenant_id`` claim scopes a request),
    signed by the server's own code under the stack's configuration -- the
    way the console's tenant switcher re-mints the token."""
    env = stack._server_env(  # pylint: disable=protected-access
        state["config"], state["code"], multitenancy=True
    )
    tenants = [t["id"] for t in state["tenants"]]
    out = subprocess.run(  # nosec B603 - fixed interpreter, our own script
        [sys.executable, "-c", _MINT, stack_mt.ADMIN, json.dumps(tenants)],
        cwd=state["code"], env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode != 0:
        raise SystemExit(
            f"could not mint the burst's tenant tokens (exit {out.returncode}):\n"
            f"{out.stderr[-3000:]}"
        )
    return json.loads(out.stdout.strip().splitlines()[-1])


async def _hosts(session, base, token) -> List[str]:
    async with session.get(
        f"{base}/api/v1/hosts", headers={"Authorization": f"Bearer {token}"}
    ) as r:
        r.raise_for_status()
        hosts = await r.json()
    return [str(h["id"]) for h in hosts if h.get("approval_status") == "approved"]


async def _probe(
    session, base, stop: asyncio.Event, out: List[float], failures: List[str]
):
    while not stop.is_set():
        started = time.monotonic()
        try:
            async with session.get(
                f"{base}/api/health", timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                await r.read()
                if r.status != 200:
                    failures.append(str(r.status))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failures.append(type(exc).__name__)
        out.append(time.monotonic() - started)
        await asyncio.sleep(PROBE_SECONDS)


async def _fire(session, base, token, host_id, gate, results):
    async with gate:
        started = time.monotonic()
        try:
            async with session.post(
                f"{base}/api/v1/host/update-agent/{host_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as r:
                await r.read()
                status = r.status
        except Exception as exc:  # pylint: disable=broad-exception-caught
            status = type(exc).__name__
        results.append((status, time.monotonic() - started))


def _queued(state, since: str) -> int:
    """update_agent commands queued in every tenant database since ``since``."""
    total = 0
    for tenant in state["tenants"]:
        engine = _engine(tenant["db_url"])
        try:
            with engine.connect() as conn:
                total += conn.execute(text(
                    "SELECT count(*) FROM message_queue WHERE direction = 'outbound' "
                    "AND message_type = 'command' AND message_data LIKE '%update_agent%' "
                    "AND created_at >= :since"
                ), {"since": since}).scalar() or 0  # fmt: skip
        finally:
            engine.dispose()
    return total


def _pool_timeouts(log_offset: int) -> int:
    log = stack.STATE_DIR / "server.log"
    with open(log, "rb") as fh:
        fh.seek(log_offset)
        return fh.read().decode("utf-8", "replace").count("QueuePool limit")


async def run_burst(state, concurrency: int) -> dict:
    """Replay "upgrade every agent" against the stack; returns the measurements."""
    base = f"http://127.0.0.1:{state['port']}"
    tokens = await asyncio.to_thread(mint_tokens, state)
    log = stack.STATE_DIR / "server.log"
    log_offset = log.stat().st_size if log.exists() else 0
    since = await asyncio.to_thread(_db_now, state)
    connector = aiohttp.TCPConnector(limit=concurrency + 8)
    async with aiohttp.ClientSession(connector=connector) as session:
        targets = []
        for token in tokens.values():
            targets += [(token, host) for host in await _hosts(session, base, token)]
        stop = asyncio.Event()
        health: List[float] = []
        health_failures: List[str] = []
        probe = asyncio.create_task(
            _probe(session, base, stop, health, health_failures)
        )
        await asyncio.sleep(2)  # a baseline before the burst
        baseline = list(health)
        gate = asyncio.Semaphore(concurrency)
        results: List[tuple] = []
        started = time.monotonic()
        await asyncio.gather(
            *(_fire(session, base, tok, host, gate, results) for tok, host in targets)
        )
        elapsed = time.monotonic() - started
        await asyncio.sleep(3)
        stop.set()
        await probe
    during = health[len(baseline) :]
    latencies = [t for _s, t in results]
    statuses: Dict[str, int] = {}
    for status, _t in results:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    queued = await asyncio.to_thread(_queued, state, since)
    return {
        "hosts": len(targets),
        "tenants": len(tokens),
        "concurrency": concurrency,
        "burst_seconds": round(elapsed, 2),
        "statuses": statuses,
        "request_p50": _pct(latencies, 0.5),
        "request_p99": _pct(latencies, 0.99),
        "request_max": round(max(latencies), 3) if latencies else None,
        "health_baseline_p50": _pct(baseline, 0.5),
        "health_p50": _pct(during, 0.5),
        "health_p99": _pct(during, 0.99),
        "health_max": round(max(during), 3) if during else None,
        "health_failures": len(health_failures),
        "queued": queued,
        "pool_timeouts": await asyncio.to_thread(_pool_timeouts, log_offset),
    }


def _db_now(state) -> str:
    engine = _engine(state["db_url"])
    try:
        with engine.connect() as conn:
            return str(conn.execute(text("SELECT now() AT TIME ZONE 'UTC'")).scalar())
    finally:
        engine.dispose()


def burst_verdict(burst: dict) -> List[str]:
    """What failed, in words (empty = passed)."""
    problems = []
    ok = sum(n for s, n in burst["statuses"].items() if s.startswith("2"))
    if ok != burst["hosts"]:
        problems.append(
            f"only {ok} of {burst['hosts']} update-agent requests answered 2xx: {burst['statuses']}"
        )
    if burst["queued"] < burst["hosts"]:
        problems.append(
            f"only {burst['queued']} of {burst['hosts']} commands were queued"
        )
    if burst["pool_timeouts"]:
        problems.append(
            f"{burst['pool_timeouts']} connection-pool timeout(s) in the server log"
        )
    if burst["health_failures"]:
        problems.append(
            f"{burst['health_failures']} health probe(s) failed during the burst"
        )
    if (burst["health_p99"] or 0) > HEALTH_P99_LIMIT:
        problems.append(
            f"health p99 {burst['health_p99']} s during the burst (limit {HEALTH_P99_LIMIT} s)"
        )
    if (burst["health_max"] or 0) > HEALTH_MAX_LIMIT:
        problems.append(
            f"health max {burst['health_max']} s during the burst (limit {HEALTH_MAX_LIMIT} s): the loop stalled"
        )
    return problems
