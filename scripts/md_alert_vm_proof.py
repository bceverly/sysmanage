#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 23.1 S7 proof: a Linux md RAID array losing a member is alerted on --
and mailed -- within seconds, and the alert resolves itself once the array
has rebuilt.  On a throwaway VM (the clock skew harness's toolchain):

  1. CREATE the VM, the agent from your working tree running as root;
     REGISTER and APPROVE it; a TEMPORARY ``hardware_health`` rule for
     arrays (and, with ``--email``, a temporary email channel bound to it);
  2. BUILD a RAID1 on two file-backed loop devices and wait for the server
     to see it healthy;
  3. FAIL one member (``mdadm --fail``): the kernel logs it, the agent
     reports at once with the evidence, the alert opens [and is mailed] --
     timed from the ``mdadm`` command;
  4. REPLACE it (``--remove`` + ``--add``): the array rebuilds, and the alert
     resolves itself;
  5. TEAR DOWN -- always: rule, channel, host, VM.

Usage:
    python3 scripts/md_alert_vm_proof.py --server http://localhost:8080 \\
        --agent-server 192.168.4.132:8080 [--enrollment-token T] \\
        [--email you@example.com]

Credentials as for the clock proof.  Exit status: 0 proven, 1 not proven,
2 the harness could not get that far.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# pylint: disable=wrong-import-position,protected-access
import clock_skew_proof as proof  # noqa: E402
import clock_skew_vm_test as vm  # noqa: E402
from hardware_alert_proof import Proof, mailed, wait  # noqa: E402

# pylint: enable=wrong-import-position

RULES = {"arrays": {"kinds": ["array"], "min_level": "warning"}}
MD = "/dev/md100"
BUILD = (
    "set -e; command -v mdadm >/dev/null || sudo DEBIAN_FRONTEND=noninteractive "
    "apt-get install -y -q mdadm >/dev/null; "
    "sudo truncate -s 64M /var/tmp/md-a /var/tmp/md-b; "
    "A=$(sudo losetup -f --show /var/tmp/md-a); "
    "B=$(sudo losetup -f --show /var/tmp/md-b); "
    "echo $A $B | sudo tee /var/tmp/md-loops; "
    f"yes | sudo mdadm --create {MD} --level=1 --raid-devices=2 --run $A $B; "
    f"sudo mdadm --wait {MD} || true"
)
FAIL = f"sudo mdadm {MD} --fail $(cut -d' ' -f2 /var/tmp/md-loops)"
REPLACE = (
    "B=$(cut -d' ' -f2 /var/tmp/md-loops); "
    f"sudo mdadm {MD} --remove $B && sudo mdadm {MD} --add $B && "
    f"sudo mdadm --wait {MD} || true"
)


def ssh(workdir: Path, command: str) -> str:
    return vm.capture(["vagrant", "ssh", "-c", command], workdir, timeout=600)


def array_state(p: Proof, hid: str):
    view = p.hardware(hid) or {}
    md = next((c for c in view.get("components", []) if c["kind"] == "array"), None)
    return md["state"] if md else None


def prove(args, p, workdir, results, hostname, state):
    vm.log(results, f"creating VM {hostname} ({args.box})")
    vm.run(
        ["vagrant", "up", "--provider=libvirt", "--no-provision"],
        workdir, results, "vagrant.log", timeout=900,
    )  # fmt: skip
    vm.run(["vagrant", "provision"], workdir, results, "vagrant.log", timeout=2400)
    host = vm.wait_for(
        results, "the agent to register",
        lambda: vm.registered_host(args, p.token, hostname), args.register_timeout,
    )  # fmt: skip
    if host is None:
        return ["the agent never registered"]
    state["host"] = host
    hid = str(host["id"])
    if host.get("approval_status") != "approved":
        p.req("PUT", f"/host/{hid}/approve")
    vm.log(results, f"registered and approved {host['fqdn']}")
    vm.log(results, "building the RAID1: " + ssh(workdir, BUILD).strip()[-200:])
    healthy = wait(
        "the array to be reported healthy",
        lambda: array_state(p, hid) == "ok",
        900,
        10,
    )
    if not healthy:
        return ["the healthy array was never reported"]
    vm.log(results, "array reported ok")
    # long-running agent, not one still doing its startup collections
    print(f"  letting the agent settle ({args.settle} s)...", flush=True)
    time.sleep(args.settle)
    problems: list = []
    started = time.monotonic()
    vm.log(results, "failing a member: " + ssh(workdir, FAIL).strip()[-200:])
    alert = wait("the arrays alert", lambda: p.open_alert(hid, "arrays"), 300, 1)
    if alert is None:
        return ["no arrays alert after a member failed"]
    vm.log(results, f"arrays alert {time.monotonic() - started:.1f} s after "
                    f"mdadm --fail: {alert['severity']} -- {alert['message']}")  # fmt: skip
    mailed(p, hid, "arrays", results, started, problems, "arrays")
    system = [
        e for e in (p.hardware(hid) or {}).get("events", []) if e["kind"] == "system"
    ]
    if system:
        vm.log(results, f"operating-system event: {system[0]['reasons'][0]}")
    else:
        problems.append("no operating-system event was recorded")
    vm.log(results, "replacing the member: " + ssh(workdir, REPLACE).strip()[-200:])
    resolved = wait(
        "the arrays alert to resolve itself",
        lambda: p.open_alert(hid, "arrays") is None,
        900,
        5,
    )
    if resolved:
        vm.log(results, "arrays alert resolved itself")
    else:
        problems.append("the arrays alert did not resolve itself")
    return problems


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True)
    parser.add_argument("--agent-server")
    parser.add_argument("--agent-https", action="store_true")
    parser.add_argument("--enrollment-token")
    parser.add_argument("--agent-src", type=Path, default=vm.DEFAULT_AGENT_SRC)
    parser.add_argument("--box", default="generic/ubuntu2204")
    parser.add_argument("--email", help="mail the alert to this address")
    parser.add_argument("--settle", type=int, default=180)
    parser.add_argument("--register-timeout", type=int, default=900)
    parser.add_argument("--results", type=Path, default=Path("hardware-proof-results"))
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    args = parser.parse_args()
    args.time_service = "timesyncd"  # the VM template needs one
    return args


def main() -> int:
    args = parse_args()
    for tool in ("vagrant", "ssh"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} is not installed.")
    p = Proof(args.server, args.token or proof._login(args.server), RULES)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = (args.results / f"md-{stamp}").resolve()
    workdir = results / "vm"
    workdir.mkdir(parents=True)
    hostname = f"mdtest-{secrets.token_hex(3)}"
    state: dict = {}
    problems, code = ["the harness stopped before the proof ran"], 2
    try:
        vm.write_vm(workdir, args, hostname)
        if args.email:
            p.create_channel(args.email)
        p.create_rules()
        problems = prove(args, p, workdir, results, hostname, state)
        code = 1 if problems else 0
    except KeyboardInterrupt:
        problems = ["interrupted"]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        problems = [f"harness error: {exc}"]
    finally:
        p.delete_rules()
        p.delete_channel()
        vm.collect(args, p.token, workdir, results, None)
        vm.tear_down(args, p.token, workdir, results, state.get("host"), hostname)
    summary = (
        f"md RAID alert proof -- {stamp}\n{'PROVEN' if code == 0 else 'NOT PROVEN'}\n"
        + "".join(f"  - {x}\n" for x in problems if code)
        + f"artifacts: {results}\n"
    )
    (results / "SUMMARY.txt").write_text(summary)
    print("\n" + summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
