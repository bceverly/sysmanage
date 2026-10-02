# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The simulated fleet on ANOTHER machine (Phase 22 scale harness).

At 10,000 agents the simulator needs as much CPU as the server it is
measuring; on one machine they starve each other and the numbers measure the
laptop.  This runs only the fleet, on a second machine; the controller
(``fleet_scenarios`` with ``--remote-fleet HOST``) keeps the server, the
database, the observer and the restart, and drives this over ssh:

    controller -> (ssh) fleet_remote.py --base http://SERVER:PORT ...
    fleet_remote: enrolls the fleet, prints "REGISTERED <n>"
    controller:   approves the hosts in its database, writes "GO\\n"
    fleet_remote: runs for --run-seconds, then prints "STATS <json>"

Every agent shares the remote machine's address (``bind_source=False``):
the large-NAT case.  Needs only aiohttp and websockets.
"""

import argparse
import asyncio
import json
import random
import sys
import time

from tests.load.fleet import COLLECTION_S, Fleet

RTT_SAMPLES = 20_000


def _sample(values: list) -> list:
    if len(values) <= RTT_SAMPLES:
        return values
    return random.Random(0).sample(values, RTT_SAMPLES)


def _stats(fleet: Fleet) -> dict:
    stats = fleet.stats
    return {
        "agents": len(fleet.agents),
        "source_ips": fleet.source_ips,
        "time_scale": fleet.time_scale,
        "counts": dict(stats.counts),
        "sent": dict(stats.sent),
        "errors_received": dict(stats.errors_received),
        # At most RTT_SAMPLES: 10,000 agents' every round trip made a line
        # of many MB (the controller reads it as one line).
        "heartbeat_rtt_ms": _sample(stats.heartbeat_rtt_ms),
        "connected_at_end": stats.connected_at_end,
        "bytes_sent": stats.bytes_sent,
        "timeline": stats.timeline,
    }


async def _ticker(fleet, started, interval):
    while True:
        await asyncio.sleep(interval)
        fleet.stats.snapshot(time.monotonic() - started)


async def run(args) -> dict:
    fleet = Fleet(args.base, args.agents, 1, args.time_scale, args.packages,
                  send_on_change=args.send_on_change, jitter=args.jitter,
                  identity_auth=args.identity_auth, bind_source=False)  # fmt: skip
    await fleet.register_all()
    print(f"REGISTERED {fleet.stats.counts['register_ok']}", flush=True)
    go = await asyncio.to_thread(sys.stdin.readline)
    if go.strip() != "GO":
        raise SystemExit(f"expected GO from the controller, got {go!r}")
    started = time.monotonic()
    ticker = asyncio.create_task(_ticker(fleet, started, args.sample_seconds))
    fleet.start(ramp_seconds=COLLECTION_S / args.time_scale)
    try:
        await asyncio.sleep(args.run_seconds)
    finally:
        ticker.cancel()
        fleet.stats.connected_at_end = fleet.stats.connected
        await fleet.stop()
    return _stats(fleet)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", required=True, help="http://SERVER:PORT")
    parser.add_argument("--agents", type=int, required=True)
    parser.add_argument("--run-seconds", type=float, required=True)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--packages", type=int, default=600)
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--send-on-change", action="store_true")
    parser.add_argument("--jitter", action="store_true")
    parser.add_argument("--identity-auth", action="store_true")
    args = parser.parse_args(argv)
    stats = asyncio.run(run(args))
    print("STATS " + json.dumps(stats, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
