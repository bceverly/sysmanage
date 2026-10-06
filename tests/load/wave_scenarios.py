# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Fleet-wide pushes go out in waves (Phase 22.3 exit criterion).

A plan or rule bump used to reach every host in one tick.  22.3 caps each
pass: antivirus auto-deploy queues at most ``MAX_PUSHES_PER_PASS`` plans per
database per pass, the package-catalog refresh at most ``MAX_ASKS_PER_PASS``
requests.  This scenario proves it end to end on the disposable server:

  1. a fleet enrolls and settles (as fleet-steady);
  2. an antivirus default is set for the fleet's OS -- every host is due at
     once, which is what a ``PLAN_VERSION`` bump does;
  3. the REAL pass functions (``av_auto_deploy.reconcile`` and
     ``package_catalog_refresh.request_refresh_for_stale_hosts``) run against
     the server's database every ``--pass-seconds`` -- the server's own ticks
     need the licensed malware engine and run every 5 minutes / hour, so the
     harness drives them, faster than production;
  4. the server's real outbound path delivers the commands; every simulated
     agent records what it received and when.

Criteria: no pass queues more than its cap; every agent gets exactly one
antivirus plan, within ceil(agents / cap) passes, and every plan is recorded
as succeeded; every agent is asked for its catalog within ceil(agents / cap)
passes; and the fleet stays healthy throughout (the fleet criteria: no
expiry, no lockout, backlog drains).
"""

import asyncio
import math
import os
import sys
import time
from collections import Counter
from typing import Dict, List

from sqlalchemy import create_engine, text

from tests.load import fleet_scenarios, stack
from tests.load.fleet import Fleet
from tests.load.observe import Observer

AV_COMMAND = "apply_deployment_plan"
CATALOG_COMMAND = "collect_available_packages"
FLEET_OS = "Ubuntu"  # payloads.SYSTEM_INFO reports "Ubuntu 24.04"
AV_PACKAGE = "clamav"


def _import_passes(state):
    """The server's pass functions, from the code under test, bound to the
    stack's database through its own config."""
    os.environ["SYSMANAGE_CONFIG_PATH"] = state["config"]
    os.environ["SYSMANAGE_MULTITENANCY"] = "false"
    os.environ["SYSMANAGE_DISABLE_EMAIL"] = "true"
    os.environ["OTEL_ENABLED"] = "false"
    if state["code"] not in sys.path:
        sys.path.insert(0, state["code"])
    # pylint: disable=import-outside-toplevel
    from backend.services import av_auto_deploy, package_catalog_refresh

    return av_auto_deploy, package_catalog_refresh


def _set_av_default(db_url: str) -> None:
    engine = create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM antivirus_default WHERE os_name = :o"),
                {"o": FLEET_OS},
            )
            conn.execute(
                text("INSERT INTO antivirus_default (id, os_name, antivirus_package, created_at, "
                     "updated_at) VALUES (gen_random_uuid(), :o, :p, now(), now())"),
                {"o": FLEET_OS, "p": AV_PACKAGE},
            )  # fmt: skip
    finally:
        engine.dispose()


def _av_record_status(db_url: str) -> Dict[str, int]:
    engine = create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT status, count(*) FROM antivirus_auto_deploy GROUP BY status"
                )
            ).all()
        return dict(rows)
    finally:
        engine.dispose()


def _one_pass(av, catalog) -> Dict[str, int]:
    """Both passes once, on the stack's database (the single-tenant main
    engine), each committed as the server's tick commits it."""
    # pylint: disable=import-outside-toplevel
    from datetime import datetime, timezone

    from sqlalchemy.orm import sessionmaker

    from backend.persistence import db as persistence_db
    from backend.persistence import models

    session_local = sessionmaker(bind=persistence_db.get_engine())
    with session_local() as session:
        queued = av.reconcile(session, "load")["queued"]
        session.commit()
    with session_local() as session:
        asked = catalog.request_refresh_for_stale_hosts(
            session, models, datetime.now(timezone.utc)
        )
        session.commit()
    return {"av_queued": queued, "catalog_asked": asked}


def _first_arrival(arrivals, command, started) -> Dict[int, float]:
    first: Dict[int, float] = {}
    for at, kind, index in arrivals:
        if kind == command and index not in first:
            first[index] = at - started
    return first


def _wave_summary(fleet, passes, pass_times, av_status, av_cap, catalog_cap) -> dict:
    agents = len(fleet.agents)
    start = pass_times[0] if pass_times else 0.0
    # Only what the passes sent: the server also asks for the catalog at
    # registration, before them.
    before = fleet.stats.command_arrivals
    arrivals = [a for a in before if a[0] >= start]
    av_per_agent = Counter(i for _, kind, i in arrivals if kind == AV_COMMAND)
    av_first = _first_arrival(arrivals, AV_COMMAND, 0.0)
    cat_first = _first_arrival(arrivals, CATALOG_COMMAND, 0.0)

    def pass_reached(first: Dict[int, float]) -> List[int]:
        """Agents first reached after each pass started (by pass index)."""
        counts = [0] * len(pass_times)
        for at in first.values():
            index = max((n for n, t in enumerate(pass_times) if t <= at), default=0)
            counts[index] += 1
        return counts

    return {
        "agents": agents,
        "passes": passes,
        "av_cap_per_pass": av_cap,
        "catalog_cap_per_pass": catalog_cap,
        "av_queued_max_per_pass": max((p["av_queued"] for p in passes), default=0),
        "catalog_asked_max_per_pass": max(
            (p["catalog_asked"] for p in passes), default=0
        ),
        "av_passes_expected": math.ceil(agents / av_cap),
        "av_passes_used": sum(1 for p in passes if p["av_queued"]),
        "catalog_passes_expected": math.ceil(agents / catalog_cap),
        "av_agents_reached": len(av_per_agent),
        "av_agents_reached_twice": sum(1 for n in av_per_agent.values() if n > 1),
        "av_reached_per_pass": pass_reached(av_first),
        "catalog_agents_reached": len(cat_first),
        "catalog_asked_before_passes": sum(
            1 for at, kind, _ in before if kind == CATALOG_COMMAND and at < start
        ),
        "catalog_reached_per_pass": pass_reached(cat_first),
        "av_record_status": av_status,
    }


def wave_verdict(wave: dict) -> List[str]:
    out = []
    agents = wave["agents"]
    if wave["av_queued_max_per_pass"] > wave["av_cap_per_pass"]:
        out.append(f"a pass queued {wave['av_queued_max_per_pass']} antivirus plans "
                   f"(cap {wave['av_cap_per_pass']})")  # fmt: skip
    if wave["catalog_asked_max_per_pass"] > wave["catalog_cap_per_pass"]:
        out.append(f"a pass asked {wave['catalog_asked_max_per_pass']} catalogs "
                   f"(cap {wave['catalog_cap_per_pass']})")  # fmt: skip
    if wave["av_passes_used"] > wave["av_passes_expected"]:
        out.append(f"the antivirus wave took {wave['av_passes_used']} passes "
                   f"(expected {wave['av_passes_expected']})")  # fmt: skip
    if wave["av_agents_reached"] < agents:
        out.append(
            f"only {wave['av_agents_reached']}/{agents} agents got the antivirus plan"
        )
    if wave["av_agents_reached_twice"]:
        out.append(
            f"{wave['av_agents_reached_twice']} agents got the antivirus plan twice"
        )
    succeeded = wave["av_record_status"].get("succeeded", 0)
    if succeeded < agents:
        out.append(f"only {succeeded}/{agents} antivirus deploys recorded as succeeded "
                   f"({wave['av_record_status']})")  # fmt: skip
    expected = wave["catalog_passes_expected"]
    in_time = sum(wave["catalog_reached_per_pass"][:expected])
    if in_time < agents:
        out.append(f"only {in_time}/{agents} agents were asked for their catalog "
                   f"within {expected} passes")  # fmt: skip
    return out


async def run_wave(args) -> dict:  # pylint: disable=too-many-locals
    if not args.reuse_stack:
        print("resetting the load stack (empty database) ...")
        await asyncio.to_thread(stack.reset)
    state = stack.load_state()
    if state.get("multitenancy"):
        raise SystemExit("fleet-wave-push runs on a single-tenant stack")
    av, catalog = _import_passes(state)
    base = f"http://127.0.0.1:{state['port']}"
    fleet = Fleet(base, args.agents, args.source_ips, args.time_scale, args.packages,
                  send_on_change=args.send_on_change, jitter=args.jitter)  # fmt: skip
    print(f"enrolling {args.agents} agents ...")
    await fleet.register_all()
    approved = await asyncio.to_thread(fleet_scenarios._approve_all, state)
    print(f"  approved {approved}")
    observer = Observer(base, state["db_url"], lambda: stack.load_state().get("server_pid"),
                        interval=args.sample_seconds)  # fmt: skip
    started = time.monotonic()
    observer.start()
    ticker = asyncio.create_task(
        fleet_scenarios._timeline(fleet, started, args.sample_seconds)
    )
    fleet.start(ramp_seconds=fleet_scenarios.COLLECTION_S / args.time_scale)
    passes, pass_times = [], []
    try:
        await asyncio.sleep(args.warmup_seconds)
        observer.mark("antivirus default set: every host due")
        await asyncio.to_thread(_set_av_default, state["db_url"])
        cap = av.MAX_PUSHES_PER_PASS
        needed = math.ceil(args.agents / cap) + 2  # two quiet passes after the wave
        for number in range(needed):
            pass_times.append(time.monotonic())
            result = await asyncio.to_thread(_one_pass, av, catalog)
            passes.append({"t": round(time.monotonic() - started, 1), **result})
            print(f"  pass {number + 1}/{needed}: {result}")
            await asyncio.sleep(args.pass_seconds)
        await asyncio.sleep(args.duration_seconds)  # results drain
    finally:
        ticker.cancel()
        fleet.stats.connected_at_end = fleet.stats.connected
        await fleet.stop()
        await observer.stop()
    av_status = await asyncio.to_thread(_av_record_status, state["db_url"])
    wave = _wave_summary(fleet, passes, pass_times, av_status,
                         av.MAX_PUSHES_PER_PASS, catalog.MAX_ASKS_PER_PASS)  # fmt: skip
    summary = fleet_scenarios._summarize(f"{args.scenario}-{args.agents}", fleet, observer,
                                         None, args.warmup_seconds)  # fmt: skip
    summary["wave"] = wave
    violations = wave_verdict(wave) + [
        v for v in fleet_scenarios.verdict(summary) if "bursty" not in v
    ]  # a wave is a burst by design; its cap is what is checked
    return {
        "scenario": args.scenario,
        "scenarios": [summary],
        "summary": summary,
        "violations": violations,
        "server_samples": observer.samples,
        "agent_timeline": fleet.stats.timeline,
    }
