#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 23.1 S6 proof: a host whose drive cannot be read without smartmontools
is recommended it, gets it, and its drive is read -- on a throwaway VM.

No lab machine has a SATA drive without smartmontools, so the VM brings one:

  1. CREATE a VM (the clock skew harness's Vagrant + libvirt toolchain) with
     an extra 1 GB SATA disk (QEMU answers SMART for it) and smartmontools
     REMOVED; the agent from your working tree runs as root;
  2. wait for it to REGISTER, APPROVE it, and wait for its hardware report:
     the SATA disk must be ``unknown`` for ``smartctl_absent``, the host
     RECOMMENDED smartmontools (host view and fleet list), and the VM's
     virtio boot disk NOT reported (no SMART there to recommend for);
  3. INSTALL -- ``--mode manual`` (default): the Install button's API call;
     ``--mode auto``: an administrator's consent (Enterprise) and the
     hardware tick does it (restored afterwards);
  4. wait for the agent to report the install SUCCEEDED, and for the next
     hardware report: the disk read by ``smartctl``, no longer unknown, and
     the recommendation gone;
  5. TEAR DOWN -- always: host deleted, VM destroyed (``--keep`` keeps both).

Usage:
    python3 scripts/smartmontools_vm_proof.py --server http://localhost:8080 \\
        --agent-server 192.168.4.132:8080 [--enrollment-token T] [--mode auto]

Credentials as for the clock proof (SYSMANAGE_TOKEN, or SYSMANAGE_USER +
SYSMANAGE_PASSWORD); the user needs Approve Host Registration, Delete Host,
Manage Hardware Health and Add Package (and administrator for ``auto``).
Exit status: 0 proven, 1 not proven, 2 the harness could not get that far.
"""

from __future__ import annotations

import argparse
import json
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

# pylint: enable=wrong-import-position

SATA_DISK = (
    '    lv.storage :file, size: "1G", bus: "sata", device: "sda"\n'
    '    lv.graphics_type = "none"\n'
)
# Run before the agent starts: the box must not have it, and nothing the
# agent's dependencies pull in may bring it back.
NO_SMARTMONTOOLS = (
    'step 4 "agent dependencies"\n'
    "apt-get remove -y -q smartmontools || true\n"
    # not `! command -v`: set -e ignores a negated command
    'if command -v smartctl; then echo "ERROR: smartctl still present" >&2; '
    "exit 1; fi\n"
)


class Server:
    def __init__(self, url: str, token: str):
        self.url, self.token = url, token

    def req(self, method, path, body=None):
        return proof._request(self.url, method, path, self.token, body)

    def hardware(self, host_id):
        status, body = self.req("GET", f"/host/{host_id}/hardware-health")
        return body if status == 200 else None

    def recommended_ids(self):
        status, body = self.req("GET", "/hardware-health/smartmontools")
        return {h["host_id"] for h in body["hosts"]} if status == 200 else set()

    def auto(self):
        _s, body = self.req("GET", "/hardware-health/smartmontools")
        return bool(body.get("auto")) if isinstance(body, dict) else False


def write_vm(workdir: Path, args, hostname: str) -> None:
    """The skew harness's VM, plus a SATA disk and minus smartmontools."""
    vm.write_vm(workdir, args, hostname)
    vagrantfile = workdir / "Vagrantfile"
    text = vagrantfile.read_text()
    vagrantfile.write_text(text.replace('    lv.graphics_type = "none"\n', SATA_DISK))
    provision = workdir / "provision.sh"
    text = provision.read_text()
    provision.write_text(
        text.replace('step 4 "agent dependencies"\n', NO_SMARTMONTOOLS)
    )
    if SATA_DISK not in vagrantfile.read_text() or NO_SMARTMONTOOLS not in (
        provision.read_text()
    ):
        raise RuntimeError("the skew harness's VM template changed; update this proof")


def bring_up(args, server, workdir, results, hostname):
    vm.log(results, f"creating VM {hostname} ({args.box}) with a SATA disk")
    vm.run(
        ["vagrant", "up", "--provider=libvirt", "--no-provision"],
        workdir, results, "vagrant.log", timeout=900,
    )  # fmt: skip
    vm.run(["vagrant", "provision"], workdir, results, "vagrant.log", timeout=2400)
    vm.log(results, "provisioned (smartctl absent)")
    host = vm.wait_for(
        results, "the agent to register",
        lambda: vm.registered_host(args, server.token, hostname), args.register_timeout,
    )  # fmt: skip
    if host is None:
        return None
    if host.get("approval_status") != "approved":
        status, _ = server.req("PUT", f"/host/{host['id']}/approve")
        if status != 200:
            raise RuntimeError(f"approving the host failed (HTTP {status})")
    vm.log(results, f"registered and approved {host['fqdn']}")
    return host


def _when(server, hid, ok):
    """A probe for ``vm.wait_for``: the host view once ``ok(view)``."""

    def probe():
        view = server.hardware(hid)
        return view if view and ok(view) else None

    return probe


def _answered(view) -> bool:
    record = (view.get("smartmontools") or {}).get("install")
    return bool(record) and record["status"] != "queued"


def _drives(view):
    return {
        c["id"]: c for c in (view or {}).get("components", []) if c["kind"] == "drive"
    }


def _absent(view) -> bool:
    sda = _drives(view).get("sda")
    return bool(sda) and any(r.get("code") == "smartctl_absent" for r in sda["reasons"])


def _read(view) -> bool:
    sda = _drives(view).get("sda")
    return bool(sda) and sda["source"] == "smartctl" and sda["state"] != "unknown"


def check_recommended(server, results, hid, problems) -> bool:
    view = vm.wait_for(
        results, "a hardware report with the SATA disk unreadable",
        _when(server, hid, _absent), 900, 10,
    )  # fmt: skip
    if view is None:
        problems.append("the SATA disk was never reported as smartctl_absent")
        return False
    (results / "hardware-before.json").write_text(json.dumps(view, indent=2))
    drives = _drives(view)
    vm.log(results, "drives before: " + ", ".join(
        f"{i} {d['state']} {d['reasons']}" for i, d in drives.items()))  # fmt: skip
    if any(i.startswith("vd") for i in drives):
        problems.append("the virtio boot disk was reported (it has no SMART)")
    if not (view.get("smartmontools") or {}).get("recommended"):
        problems.append("the host view did not recommend smartmontools")
    if hid not in server.recommended_ids():
        problems.append("the fleet list did not include the host")
    return True


def install(args, server, results, hid, state, problems) -> None:
    if args.mode == "manual":
        status, body = server.req(
            "POST", "/hardware-health/smartmontools/install", {"host_ids": [hid]}
        )
        vm.log(results, f"install requested (HTTP {status}): {body}")
        if status != 200 or body.get("queued") != 1:
            problems.append(f"the install request was not queued: {body}")
        return
    state["auto_was"] = server.auto()
    status, body = server.req("PUT", "/hardware-health/smartmontools", {"auto": True})
    vm.log(results, f"automatic install consented (HTTP {status}): {body}")
    if status != 200:
        problems.append(f"consent refused (HTTP {status}): {body}")
    else:
        state["auto_set"] = True


def check_installed(server, results, hid, problems, mode) -> None:
    started = time.monotonic()
    # auto: the tick runs every 5 minutes after up to 2 minutes' start splay
    view = vm.wait_for(
        results, "the agent to report the install succeeded",
        _when(server, hid, _answered),
        900 if mode == "auto" else 600, 10,
    )  # fmt: skip
    if view is None:
        problems.append("the agent never answered the install")
        return
    record = view["smartmontools"]["install"]
    vm.log(results, f"install {record['status']} by {record['requested_by']} "
                    f"after {time.monotonic() - started:.0f} s")  # fmt: skip
    if record["status"] != "succeeded":
        problems.append(f"the install failed: {record.get('last_error')}")
        return
    if mode == "auto" and record["requested_by"] != "system:smartmontools-auto-install":
        problems.append(f"installed by {record['requested_by']}, not automatically")
    # the agent re-collects every five minutes
    view = vm.wait_for(
        results, "the next hardware report to read the disk",
        _when(server, hid, _read), 600, 10,
    )  # fmt: skip
    if view is None:
        problems.append("the SATA disk was still not read by smartctl")
        return
    (results / "hardware-after.json").write_text(json.dumps(view, indent=2))
    sda = _drives(view)["sda"]
    vm.log(results, f"sda now {sda['state']} via smartctl ({sda['name']}), "
                    f"{time.monotonic() - started:.0f} s after the request")  # fmt: skip
    if view["smartmontools"]["recommended"] or hid in server.recommended_ids():
        problems.append("still recommended after the disk became readable")


def prove(args, server, workdir, results, hostname, state):
    host = bring_up(args, server, workdir, results, hostname)
    if host is None:
        return ["the agent never registered"]
    state["host"] = host
    hid = str(host["id"])
    problems: list = []
    if check_recommended(server, results, hid, problems):
        install(args, server, results, hid, state, problems)
        if not problems:
            check_installed(server, results, hid, problems, args.mode)
    return problems


def restore(server, results, state) -> None:
    if state.get("auto_set") and not state.get("auto_was"):
        status, _ = server.req("PUT", "/hardware-health/smartmontools", {"auto": False})
        vm.log(results, f"automatic install consent withdrawn again (HTTP {status})")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True)
    parser.add_argument("--agent-server")
    parser.add_argument("--agent-https", action="store_true")
    parser.add_argument("--enrollment-token")
    parser.add_argument("--agent-src", type=Path, default=vm.DEFAULT_AGENT_SRC)
    parser.add_argument("--box", default="generic/ubuntu2204")
    parser.add_argument("--mode", choices=("manual", "auto"), default="manual")
    parser.add_argument("--register-timeout", type=int, default=900)
    parser.add_argument("--results", type=Path, default=Path("hardware-proof-results"))
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    args = parser.parse_args()
    args.time_service = "timesyncd"  # the box's own; the VM template needs one
    return args


def main() -> int:
    args = parse_args()
    for tool in ("vagrant", "ssh"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} is not installed.")
    server = Server(args.server, args.token or proof._login(args.server))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = (args.results / f"smartmontools-{stamp}").resolve()
    workdir = results / "vm"
    workdir.mkdir(parents=True)
    hostname = f"smarttest-{secrets.token_hex(3)}"
    state: dict = {}
    problems, code = ["the harness stopped before the proof ran"], 2
    try:
        write_vm(workdir, args, hostname)
        problems = prove(args, server, workdir, results, hostname, state)
        code = 1 if problems else 0
    except KeyboardInterrupt:
        problems = ["interrupted"]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        problems = [f"harness error: {exc}"]
    finally:
        restore(server, results, state)
        vm.collect(args, server.token, workdir, results, None)
        vm.tear_down(args, server.token, workdir, results, state.get("host"), hostname)
    verdict = "PROVEN" if code == 0 else "NOT PROVEN"
    summary = (
        f"smartmontools proof ({args.mode}) -- {stamp}\n{verdict}\n"
        + "".join(f"  - {p}\n" for p in problems if code)
        + f"artifacts: {results}\n"
    )
    (results / "SUMMARY.txt").write_text(summary)
    print("\n" + summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
