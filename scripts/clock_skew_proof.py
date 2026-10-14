#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
Phase 23.3 proof: a host's clock is set wrong, SysManage sees it, says so, and
puts it back.

Against a real server and a test host whose agent runs in privileged mode,
reachable over SSH -- Linux or FreeBSD with passwordless sudo, or Windows
with an administrator account (OpenSSH gives it an elevated session):

  1. the host is measured in bounds to start with;
  2. its time service is stopped and its clock set ``--skew`` seconds ahead
     (``date -s`` / ``date -f %s`` / ``Set-Date``) -- the stopped service is
     the S0 laptop's real failure;
  3. the server MEASURES the new offset (within ``--tolerance`` seconds of the
     skew) and reports the host critical -- from the heartbeat exchange, not
     from the host's own word;
  4. with ``--expect-alert`` (Enterprise, a ``clock_offset`` rule): an open
     alert for the host -- the rule's cooldown must have passed since the
     host's last clock alert (a resolved alert still counts toward it, by
     design), so give a test rule a short one;
  5. ``Resynchronize now`` (the API the button calls) steps the clock back;
  6. the host is measured in bounds again -- and, with ``--expect-alert``,
     the alert resolved itself.

The host's time service is ALWAYS put back as it was found -- started again
if it was running, stopped again if it was not -- pass or fail.

Usage:
    python3 scripts/clock_skew_proof.py --server https://sysmanage.lan \\
        --host skewtest-vm --ssh admin@skewtest-vm [--skew 120] [--expect-alert]
    (``--host-id`` instead of ``--host`` when several hosts share the name)

Credentials: ``--token`` (or SYSMANAGE_TOKEN), or SYSMANAGE_USER +
SYSMANAGE_PASSWORD.  ``--insecure`` skips TLS verification for a lab server.
Exit status: 0 proven, 1 not proven, 2 could not ask.
"""

import argparse
import base64
import json
import os
import re
import shlex
import ssl
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request

_CONTEXT = None
_SSH_CONFIG = None
_SSH_TARGET = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.:-]+$|^[A-Za-z0-9.:-]+$")
# The agent's service name -> the units it can be, per OS.
_UNITS = {
    "linux": {
        "chrony": ("chronyd", "chrony"),
        "timesyncd": ("systemd-timesyncd",),
        "ntpd": ("ntpsec", "ntp", "ntpd"),
    },
    "freebsd": {
        "ntpd": ("ntpd",),
        "chrony": ("chronyd",),
        "openntpd": ("openntpd",),
    },
    "windows": {"w32time": ("w32time",)},
}
# ssh's own chatter on stderr, and PowerShell's progress records.
_NOISE = ("** ", "#< CLIXML", "<Objs ")


def _request(server, method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        f"{server.rstrip('/')}/api/v1{path}", data=data, method=method
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(
            req, timeout=30, context=_CONTEXT
        ) as resp:  # nosec B310
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _login(server):
    user, password = os.environ.get("SYSMANAGE_USER"), os.environ.get(
        "SYSMANAGE_PASSWORD"
    )
    if not (user and password):
        sys.exit(
            "Give --token (or SYSMANAGE_TOKEN), or SYSMANAGE_USER + SYSMANAGE_PASSWORD."
        )
    status, body = _request(
        server, "POST", "/login", body={"userid": user, "password": password}
    )
    token = (body or {}).get("Authorization") or (body or {}).get("access_token")
    if status != 200 or not token:
        print(
            f"Login failed (HTTP {status}); with MFA on, use --token.", file=sys.stderr
        )
        sys.exit(2)
    return token.replace("Bearer ", "")


def _ps(script):
    """A PowerShell command line for Windows' sshd (which hands it to cmd):
    encoded, so no quoting survives cmd.exe's rules."""
    script = "$ProgressPreference = 'SilentlyContinue'\n" + script
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    return f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}"


def _ssh(target, command):
    """Run ``command`` (a fixed string built here) on the test host."""
    result = subprocess.run(  # nosec B603 B607
        [
            "ssh",
            *(["-F", _SSH_CONFIG] if _SSH_CONFIG else []),
            "-o",
            "BatchMode=yes",
            target,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    lines = (result.stdout + result.stderr).splitlines()
    return (
        result.returncode,
        "\n".join(line for line in lines if not line.startswith(_NOISE)).strip(),
    )


def remote_os(target):
    """linux / freebsd / windows (others are not supported), or None."""
    rc, out = _ssh(target, "uname -s")
    if rc == 0 and out:
        return out.splitlines()[-1].strip().lower()
    _rc, out = _ssh(target, "ver")
    return "windows" if "windows" in out.lower() else None


def _service_cmd(os_name, unit, action):
    """exists / running / stop / start ``unit`` (a name from _UNITS)."""
    q = shlex.quote(unit)
    if os_name == "windows":
        return _ps(
            {
                "exists": f"Get-Service -Name {unit} -ErrorAction Stop | Out-Null",
                "running": f"if ((Get-Service -Name {unit}).Status -ne 'Running') "
                "{ exit 1 }",
                "stop": f"Stop-Service -Name {unit} -Force -ErrorAction Stop",
                "start": f"Start-Service -Name {unit} -ErrorAction Stop",
            }[action]
        )
    if os_name == "freebsd":
        return {
            "exists": f"test -x /etc/rc.d/{q} -o -x /usr/local/etc/rc.d/{q}",
            "running": f"service {q} onestatus",
            "stop": f"sudo service {q} onestop",
            "start": f"sudo service {q} onestart",
        }[action]
    return {
        "exists": f"systemctl cat {q} >/dev/null 2>&1",
        "running": f"systemctl is-active --quiet {q}",
        "stop": f"sudo systemctl stop {q}",
        "start": f"sudo systemctl start {q}",
    }[action]


def _skew_cmd(os_name, seconds):
    seconds = int(seconds)
    if os_name == "windows":
        return _ps(f"Set-Date -Adjust ([TimeSpan]::FromSeconds({seconds})) | Out-Null")
    if os_name == "freebsd":
        return f"sudo sh -c 'date -f %s $(( $(date +%s) + {seconds} ))'"
    return f"sudo date -u -s @$(( $(date +%s) + {seconds} ))"


def find_unit(target, os_name, service):
    """The unit the agent's ``service`` runs as, and whether it is running."""
    for unit in _UNITS.get(os_name, {}).get(service, ()):
        if _ssh(target, _service_cmd(os_name, unit, "exists"))[0] == 0:
            running = _ssh(target, _service_cmd(os_name, unit, "running"))[0] == 0
            return unit, running
    return None, False


def set_service(target, os_name, unit, running):
    """Start or stop ``unit``; True when it is then in that state."""
    _ssh(target, _service_cmd(os_name, unit, "start" if running else "stop"))
    now = _ssh(target, _service_cmd(os_name, unit, "running"))[0] == 0
    return now == running


def _find_host(server, token, name, host_id=None):
    status, hosts = _request(server, "GET", "/hosts", token)
    if status != 200 or not isinstance(hosts, list):
        print(f"Could not list hosts (HTTP {status}).", file=sys.stderr)
        sys.exit(2)
    if host_id:
        matches = [h for h in hosts if str(h.get("id")) == host_id]
    else:
        matches = [
            h
            for h in hosts
            if h.get("fqdn") == name or (h.get("fqdn") or "").split(".")[0] == name
        ]
    if len(matches) != 1:
        print(f"Host {host_id or name!r}: {len(matches)} matches.", file=sys.stderr)
        sys.exit(2)
    return matches[0]


def _clock(server, token, host_id):
    status, clock = _request(server, "GET", f"/host/{host_id}/clock", token)
    return clock if status == 200 and isinstance(clock, dict) else None


def _wait(what, probe, timeout, interval=10):
    """Poll ``probe`` until it returns a truthy value or ``timeout`` passes."""
    deadline = time.monotonic() + timeout
    print(f"  waiting for {what} (up to {timeout} s)...", flush=True)
    while time.monotonic() < deadline:
        found = probe()
        if found:
            return found
        time.sleep(interval)
    return None


def _offset_s(clock):
    measured = (clock or {}).get("measured") or {}
    offset = measured.get("offset_ms")
    return None if offset is None else offset / 1000.0


def _clock_rule_ids(server, token, enabled_only=False):
    status, rules = _request(server, "GET", "/alerting/rules", token)
    rules = rules.get("rules", rules) if isinstance(rules, dict) else rules
    if status != 200 or not isinstance(rules, list):
        return set()
    return {
        str(r["id"])
        for r in rules
        if r.get("condition_type") == "clock_offset"
        and (r.get("enabled") or not enabled_only)
    }


def _open_alert(server, token, host_id):
    """The host's open alert from a ``clock_offset`` rule, or None.  (The
    alert list returns open alerts only.)"""
    rule_ids = _clock_rule_ids(server, token)
    status, body = _request(
        server, "GET", f"/alerting/alerts?host_id={host_id}&limit=100", token
    )
    alerts = body.get("alerts", body) if isinstance(body, dict) else body
    if status != 200 or not isinstance(alerts, list):
        return None
    return next(
        (
            a
            for a in alerts
            if str(a.get("rule_id")) in rule_ids and not a.get("resolved_at")
        ),
        None,
    )


def pending_resync(server, token, host_id):
    """The host's resync still queued or sent, or None."""
    _s, body = _request(server, "GET", f"/time-sync/resyncs?host_id={host_id}", token)
    rows = (body or {}).get("resyncs") or []
    return next((r for r in rows if r.get("status") in ("queued", "sent")), None)


def _request_resync(server, token, host_id, timeout):
    """POST a resync; when one is already running (409), wait for it to
    finish and ask once more.  Returns (status, row)."""
    status, resync = _request(server, "POST", f"/host/{host_id}/clock/resync", token)
    if status == 409:
        _wait(
            "the resync already running to finish",
            lambda: pending_resync(server, token, host_id) is None,
            timeout,
            interval=5,
        )
        status, resync = _request(
            server, "POST", f"/host/{host_id}/clock/resync", token
        )
    return status, resync


def _prove(args, server, token, host, problems, found):
    """The proof proper.  ``found`` collects what main() must put back: the
    time service's unit and whether it was running, and whether the clock is
    still skewed (set, but no resync has succeeded)."""
    host_id = host["id"]
    before = _clock(server, token, host_id)
    if before is None:
        problems.append("could not read the host's clock")
        return
    print(f"  start: status {before['status']}, offset {_offset_s(before)} s")
    if before["status"] != "ok":
        problems.append(f"the host is not in bounds to start with ({before['status']})")
        return
    service = (before.get("time_service") or {}).get("service")
    if not service:
        problems.append("the host has not reported its time service yet")
        return
    unit, running = find_unit(args.ssh, found["os"], service)
    if unit is None:
        problems.append(f"no {service} unit found on the host ({found['os']})")
        return
    found.update(unit=unit, running=running)
    if running and not set_service(args.ssh, found["os"], unit, False):
        # A running service would pull the clock straight back.
        problems.append(f"could not stop the time service ({service})")
        return
    print(
        f"  {'stopped' if running else 'already stopped:'} the time service "
        f"({service}, unit {unit})"
    )
    rc, out = _ssh(args.ssh, _skew_cmd(found["os"], args.skew))
    if rc != 0:
        problems.append(f"could not set the clock: {out}")
        return
    found["skewed"] = True

    def skewed():
        clock = _clock(server, token, host_id)
        offset = _offset_s(clock)
        if offset is not None and abs(offset - args.skew) <= args.tolerance:
            return clock
        return None

    clock = _wait(f"an offset of +{args.skew} s", skewed, args.timeout)
    if clock is None:
        problems.append(f"the server never measured an offset near +{args.skew} s")
        return
    print(f"  measured: {_offset_s(clock):+.3f} s, status {clock['status']}")
    if clock["status"] != "critical":
        problems.append(f"expected critical, the server says {clock['status']}")
    if args.expect_alert and not _wait(
        "an open clock alert",
        lambda: _open_alert(server, token, host_id),
        args.timeout,
    ):
        problems.append("no open clock alert for the host")

    status, resync = _request_resync(server, token, host_id, args.timeout)
    if status != 200:
        problems.append(f"resync was refused (HTTP {status})")
        return

    def finished():
        _s, body = _request(
            server, "GET", f"/time-sync/resyncs?host_id={host_id}", token
        )
        rows = (body or {}).get("resyncs") or []
        row = next((r for r in rows if r["id"] == resync["id"]), None)
        return row if row and row["status"] not in ("queued", "sent") else None

    row = _wait("the resync result", finished, args.timeout, interval=5)
    if row is None or row["status"] != "succeeded":
        problems.append(f"resync did not succeed: {row}")
        return
    found["skewed"] = False
    print(f"  resync: {row['method']} succeeded")

    def recovered():
        clock = _clock(server, token, host_id)
        return clock if clock and clock["status"] == "ok" else None

    clock = _wait("the clock back in bounds", recovered, args.timeout)
    if clock is None:
        problems.append("the clock was never measured in bounds again")
        return
    print(f"  recovered: {_offset_s(clock):+.3f} s, status ok")
    if args.expect_alert and not _wait(
        "the alert to resolve itself",
        lambda: _open_alert(server, token, host_id) is None,
        args.timeout,
    ):
        problems.append("the clock alert did not resolve itself")
    return


def main():
    global _CONTEXT, _SSH_CONFIG  # pylint: disable=global-statement
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--host", help="the test host's FQDN or short name")
    which.add_argument("--host-id", help="the test host's id on the server")
    parser.add_argument(
        "--ssh", required=True, help="ssh target, e.g. admin@skewtest-vm"
    )
    parser.add_argument(
        "--ssh-config", help="an ssh config file (e.g. from vagrant ssh-config)"
    )
    parser.add_argument("--skew", type=float, default=120.0, help="seconds ahead")
    parser.add_argument("--tolerance", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--expect-alert", action="store_true")
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()
    if not args.server.lower().startswith(("https://", "http://")):
        sys.exit("--server must be an http:// or https:// URL.")
    if not _SSH_TARGET.match(args.ssh):
        sys.exit("--ssh must be user@host or host.")
    if not 10 <= args.skew <= 1500:
        sys.exit(
            "--skew must be 10-1500 s (under the server's 30-minute message limit)."
        )
    if args.ssh_config:
        if not os.path.isfile(args.ssh_config):
            sys.exit("--ssh-config: no such file.")
        _SSH_CONFIG = args.ssh_config
    if args.insecure:
        # Lab servers with a self-signed certificate only; opt-in.
        # nosemgrep
        _CONTEXT = ssl._create_unverified_context()  # nosec B323
    token = args.token or _login(args.server)
    if args.expect_alert and not _clock_rule_ids(args.server, token, True):
        print(
            "--expect-alert: the server has no enabled clock_offset alert rule "
            "(Enterprise alerting) -- create one first.",
            file=sys.stderr,
        )
        return 2
    host = _find_host(args.server, token, args.host, args.host_id)
    found = {"os": remote_os(args.ssh), "unit": None, "running": False}
    found["skewed"] = False
    if found["os"] not in _UNITS:
        print(f"Unsupported host OS: {found['os']}.", file=sys.stderr)
        return 2
    print(f"{host['fqdn']} ({found['os']})")
    problems = []
    try:
        _prove(args, args.server, token, host, problems, found)
    finally:
        if found["skewed"]:
            # A real machine must not be left off by --skew.
            rc, _out = _ssh(args.ssh, _skew_cmd(found["os"], -args.skew))
            print(
                f"  clock stepped back {args.skew:g} s"
                if rc == 0
                else f"  COULD NOT step the clock back {args.skew:g} s -- do it by hand"
            )
        if found["unit"]:
            ok = set_service(args.ssh, found["os"], found["unit"], found["running"])
            state = "started" if found["running"] else "stopped"
            print(
                f"  {found['unit']} {state} again, as it was found"
                if ok
                else f"  COULD NOT put {found['unit']} back ({state}) -- do it by hand"
            )
    print()
    if problems:
        print("NOT PROVEN:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    alert = ", raised its alert, " if args.expect_alert else ", "
    print(
        f"PROVEN: a clock set {args.skew:+.0f} s off was measured, reported critical"
        f"{alert}resynchronized and measured in bounds again"
        + (" -- and the alert resolved itself." if args.expect_alert else ".")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
