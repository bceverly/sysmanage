#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 23.1 proof: a failing disk on a real machine is seen, alerted on within
seconds, and the alert resolves itself when the disk comes back.

On a FreeBSD host you can SSH into with passwordless sudo, and a server with
Enterprise alerting:

  1. two TEMPORARY ``hardware_health`` rules: one for drives, one for pools
     -- with no notification channel, so nothing is mailed, unless
     ``--email ADDRESS``: then a temporary email channel to that address is
     bound to both, and each alert must be MAILED (the server's SMTP send
     succeeded) -- timed from the failure;
  2. the agent from your working tree runs on the host as root, as a NEW host
     (``clock_skew_host_test.Remote``: test config, original put back);
  3. the host's hardware report arrives; the drives rule opens an alert for
     any drive that is not ok (the lab box's SSD has 19 media errors);
  4. a disposable file-backed ZFS mirror is created and one side OFFLINED:
     devd announces it, the agent reports at once with the evidence, the
     server records an "operating system" event, and the pools rule opens an
     alert -- the time from ``zpool offline`` to the open alert is measured;
  5. the side is brought back ONLINE: the pool is healthy again and the pools
     alert resolves itself (on the agent's next report);
  6. EVERYTHING is undone -- pool destroyed, agent stopped, host deleted,
     config restored, rules deleted -- pass or fail.

Usage:
    python3 scripts/hardware_alert_proof.py --server http://sysmanage.lan:8080 \\
        --ssh freebsd --agent-server 192.168.4.132:8080 [--enrollment-token T] \\
        [--email you@example.com]

Credentials as for the clock proof.  Exit status: 0 proven, 1 not proven,
2 could not get as far as testing.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# pylint: disable=wrong-import-position,protected-access
import clock_skew_proof as proof  # noqa: E402
from clock_skew_host_test import CONFIG, Remote  # noqa: E402
from clock_skew_vm_test import DEFAULT_AGENT_SRC, agent_endpoint, log  # noqa: E402

# pylint: enable=wrong-import-position

POOL = "sm23proof"
RULES = {
    "drives": {"kinds": ["drive"], "min_level": "warning"},
    "pools": {"kinds": ["pool"], "min_level": "warning"},
}


class Proof:
    """The server side: rules, host, alerts, events."""

    def __init__(self, server: str, token: str, rules=None):
        self.server, self.token = server, token
        self.rule_params = rules or RULES
        self.rules = {}
        self.channel = None

    def create_channel(self, address):
        status, channel = self.req(
            "POST",
            "/alerting/channels",
            {
                "name": "Hardware proof email (temporary)",
                "channel_type": "email",
                "config": {"recipients": [address]},
                "enabled": True,
            },
        )
        if status != 200:
            raise RuntimeError(f"creating the email channel failed (HTTP {status})")
        self.channel = channel["id"]

    def delete_channel(self):
        if self.channel:
            self.req("DELETE", f"/alerting/channels/{self.channel}")

    def req(self, method, path, body=None):
        return proof._request(self.server, method, path, self.token, body)

    def create_rules(self):
        for name, params in self.rule_params.items():
            status, rule = self.req(
                "POST",
                "/alerting/rules",
                {
                    "name": f"Hardware proof ({name}, temporary)",
                    "description": "Phase 23.1 proof; deleted by the script",
                    "condition_type": "hardware_health",
                    "condition_params": {**params, "respect_maintenance": False},
                    "severity": "high",
                    "enabled": True,
                    "cooldown_minutes": 1,
                    "channel_ids": [self.channel] if self.channel else [],
                },
            )
            if status != 200:
                raise RuntimeError(f"creating the {name} rule failed (HTTP {status})")
            self.rules[name] = rule["id"]

    def delete_rules(self):
        for rule_id in self.rules.values():
            self.req("DELETE", f"/alerting/rules/{rule_id}")

    def open_alert(self, host_id, rule):
        _s, body = self.req("GET", f"/alerting/alerts?host_id={host_id}&limit=100")
        alerts = body.get("alerts", body) if isinstance(body, dict) else body
        return next(
            (
                a
                for a in alerts or []
                if str(a.get("rule_id")) == str(self.rules[rule])
                and not a.get("resolved_at")
            ),
            None,
        )

    def hardware(self, host_id):
        status, body = self.req("GET", f"/host/{host_id}/hardware-health")
        return body if status == 200 else None


def wait(what, probe, timeout, interval=2.0):
    print(f"  waiting for {what} (up to {timeout} s)...", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = probe()
        if found:
            return found
        time.sleep(interval)
    return None


def mailed(p, hid, rule, results, started, problems, what):
    """With --email: the alert's notification was sent (SMTP accepted it)."""
    if not p.channel:
        return

    def sent():
        alert = p.open_alert(hid, rule)
        return alert if alert and alert.get("notification_sent") else None

    alert = wait(f"the {what} email", sent, 120, 1)
    if alert is None:
        problems.append(f"the {what} alert was never mailed")
        return
    log(results, f"{what} alert MAILED {time.monotonic() - started:.1f} s after "
                 f"the failure: [{alert['severity'].upper()}] {alert['title']}")  # fmt: skip


def register(args, p, remote, results, state):
    """Ship + start the agent, register and approve the host."""
    if not remote.check_python():
        raise RuntimeError(f"no usable agent interpreter at {remote.python}")
    if not remote.ship(args.agent_src):
        raise RuntimeError("could not ship the agent")
    host, port, https = agent_endpoint(args)
    security = ""
    if args.enrollment_token:
        security = f"security:\n  enrollment_token: '{args.enrollment_token}'\n"
    if not remote.write_config(
        CONFIG.format(
            host=host,
            port=port,
            https="true" if https else "false",
            log=remote.log,
            db=remote.db,
            security=security,
        )
    ):
        raise RuntimeError(f"could not write {remote.config}")
    # only now is there a config to put back (restoring one never written
    # would DELETE the host's real config)
    state["config"] = True
    _s, hosts = p.req("GET", "/hosts")
    known = {str(h["id"]) for h in hosts or []}
    if not remote.start_agent():
        raise RuntimeError("could not start the agent")
    state["agent"] = True
    name = remote.hostname()

    def new_host():
        _s, now = p.req("GET", "/hosts")
        return next(
            (
                h
                for h in now or []
                if (h.get("fqdn") or "").split(".")[0].lower() == name
                and str(h["id"]) not in known
            ),
            None,
        )

    found = wait(f"{name} to register", new_host, 600, 5)
    if found is None:
        raise RuntimeError("the agent never registered")
    if found.get("approval_status") != "approved":
        p.req("PUT", f"/host/{found['id']}/approve")
    log(results, f"registered and approved {found['fqdn']}")
    return found


def prove(args, p, remote, results, state):
    host = register(args, p, remote, results, state)
    state["host"] = host
    hid = str(host["id"])
    reported = wait(
        "the first hardware report",
        lambda: (p.hardware(hid) or {}).get("status") not in (None, "unmeasured")
        and p.hardware(hid),
        600, 5,
    )  # fmt: skip
    if not reported:
        return ["no hardware report arrived"]
    drives = [c for c in reported["components"] if c["kind"] == "drive"]
    log(
        results,
        "drives: "
        + ", ".join(f"{c['id']} {c['state']} {c['reasons']}" for c in drives),
    )
    problems = []
    if any(c["state"] != "ok" for c in drives):
        started = time.monotonic()
        alert = wait("the drives alert", lambda: p.open_alert(hid, "drives"), 180)
        if alert:
            log(results, f"drives alert: {alert['severity']} -- {alert['message']}")
            mailed(p, hid, "drives", results, started, problems, "drives")
        else:
            problems.append("a drive is not ok but no drives alert opened")
    # A fresh agent spends its first minutes on its startup collections
    # (packages, users, ...); a long-running one -- the real case -- does not.
    # Measure the real case.
    print(f"  letting the agent settle ({args.settle} s)...", flush=True)
    time.sleep(args.settle)
    # the pool: create, offline one side, time the alert
    d = f"{remote.dir}/{POOL}"
    remote.sh(f"sudo rm -rf {d}; mkdir -p {d} && truncate -s 128M {d}/a {d}/b && "
              f"sudo zpool create {POOL} mirror {d}/a {d}/b")  # fmt: skip
    state["pool"] = True
    time.sleep(5)
    started = time.monotonic()
    remote.sh(f"sudo zpool offline {POOL} {d}/b")
    alert = wait(
        "the pools alert after zpool offline",
        lambda: p.open_alert(hid, "pools"),
        300,
        1,
    )
    if alert is None:
        problems.append("no pools alert after a vdev was offlined")
        return problems
    log(results, f"pools alert {time.monotonic() - started:.1f} s after zpool offline: "
                 f"{alert['severity']} -- {alert['message']}")  # fmt: skip
    mailed(p, hid, "pools", results, started, problems, "pools")
    events = (p.hardware(hid) or {}).get("events", [])
    system = [e for e in events if e["kind"] == "system"]
    if system:
        log(results, f"operating-system event recorded: {system[0]['reasons'][0]}")
    else:
        problems.append("no operating-system event was recorded")
    remote.sh(f"sudo zpool online {POOL} {d}/b")
    resolved = wait(
        "the pools alert to resolve itself",
        lambda: p.open_alert(hid, "pools") is None,
        600,
        5,
    )
    if not resolved:
        problems.append("the pools alert did not resolve itself")
    else:
        log(results, "pools alert resolved itself")
    return problems


def cleanup(p, remote, results, state):
    if state.get("agent"):
        lines = [
            line
            for line in remote.read_log().splitlines()
            if "hardware" in line.lower() or "Queued outbound message: hardware" in line
        ]
        (results / "agent-hardware.log").write_text("\n".join(lines) + "\n")
    if state.get("pool"):
        remote.sh(f"sudo zpool destroy -f {POOL}")
        log(results, f"destroyed {POOL}")
    if state.get("agent"):
        remote.stop_agent()
    if state.get("host"):
        p.req("DELETE", f"/host/{state['host']['id']}")
        log(results, "deleted the test host")
    if state.get("config"):
        log(results, remote.restore_config())
    remote.remove_dir()
    p.delete_rules()
    log(results, "deleted the temporary rules")
    if p.channel:
        p.delete_channel()
        log(results, "deleted the temporary email channel")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True)
    parser.add_argument("--ssh", required=True)
    parser.add_argument("--agent-server")
    parser.add_argument("--agent-https", action="store_true")
    parser.add_argument("--enrollment-token")
    parser.add_argument("--agent-src", type=Path, default=DEFAULT_AGENT_SRC)
    parser.add_argument("--remote-python")
    parser.add_argument("--email", help="mail each alert to this address")
    parser.add_argument(
        "--settle", type=int, default=180, help="seconds before the pool test"
    )
    parser.add_argument("--results", type=Path, default=Path("hardware-proof-results"))
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    args = parser.parse_args()
    os_name = proof.remote_os(args.ssh)
    if os_name != "freebsd":
        sys.exit(
            f"{args.ssh}: {os_name} -- the proof needs a FreeBSD host (devd + ZFS)."
        )
    token = args.token or proof._login(args.server)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = (args.results / stamp).resolve()
    results.mkdir(parents=True)
    p, remote = Proof(args.server, token), Remote(args.ssh, os_name, args.remote_python)
    state = {}
    try:
        if args.email:
            p.create_channel(args.email)
        p.create_rules()
        problems = prove(args, p, remote, results, state)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        problems = [f"harness error: {exc}"]
    finally:
        cleanup(p, remote, results, state)
    print()
    if problems:
        print("NOT PROVEN:\n" + "\n".join(f"  - {x}" for x in problems))
        return 1
    print("PROVEN: a failing disk was alerted on within seconds and resolved itself.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
