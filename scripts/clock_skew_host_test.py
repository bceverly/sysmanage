#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
The Phase 23.3 skew proof, end to end, on a REAL machine you can SSH into --
FreeBSD (passwordless sudo) or Windows (an administrator account) -- where
``clock_skew_vm_test.py`` builds a throwaway Linux VM.

  1. SHIP the agent from your working tree (``--agent-src``) to a scratch
     directory on the host, and run it privileged (root through sudo, or
     SYSTEM through a scheduled task) with the host's existing agent venv
     (``--remote-python``), so nothing is built there;
  2. its configuration is a test one, written where the agent looks first
     (``/etc/sysmanage-agent.yaml`` or
     ``C:\\ProgramData\\SysManage\\sysmanage-agent.yaml``) -- the file that
     was there is backed up and PUT BACK at the end;
  3. wait for it to REGISTER as a new host, APPROVE it, and wait for its
     clock to be measured and its time service reported; a clock already
     out of bounds is resynchronized first, so the proof starts in bounds;
  4. RUN ``clock_skew_proof.py`` against it;
  5. CAPTURE everything into ``--results/<UTC timestamp>/``;
  6. TEAR DOWN -- always, pass or fail or Ctrl-C: the test agent stopped, its
     host deleted from the server, the configuration put back, the time
     service put back as it was found (running or stopped), the scratch
     directory removed.  ``--keep`` keeps the agent, host and directory.

Usage:
    python3 scripts/clock_skew_host_test.py --server http://sysmanage.lan:8080 \\
        --ssh freebsd --agent-server 192.168.4.132:8080 [--enrollment-token T]

Credentials as for the proof: ``--token`` / SYSMANAGE_TOKEN (an API key
works), or SYSMANAGE_USER + SYSMANAGE_PASSWORD.

Exit status: the proof's (0 proven, 1 not proven), or 2 when the harness
itself could not get as far as running it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# pylint: disable=wrong-import-position
import clock_skew_proof as proof  # noqa: E402
from clock_skew_vm_test import (  # noqa: E402
    DEFAULT_AGENT_SRC,
    RSYNC_EXCLUDE,
    agent_endpoint,
    log,
    wait_for,
)

# pylint: enable=wrong-import-position

TASK = "SysManageSkewTest"
LAYOUT = {
    "freebsd": {
        # Under the SSH user's home, not /tmp: root writes here.
        "dir": "~/.sysmanage-skewtest",
        "config": "/etc/sysmanage-agent.yaml",
        "python": "~/dev/sysmanage-agent/.venv/bin/python",
    },
    "windows": {
        "dir": "C:\\ProgramData\\SysManage\\skewtest",
        "config": "C:\\ProgramData\\SysManage\\sysmanage-agent.yaml",
        "python": "~\\dev\\sysmanage-agent\\.venv\\Scripts\\python.exe",
    },
}
CONFIG = """# Written by clock_skew_host_test.py -- the original is put back after.
server:
  hostname: '{host}'
  port: {port}
  use_https: {https}
  verify_ssl: false
client:
  registration_retry_interval: 15
  max_registration_retries: -1
logging:
  level: 'INFO|WARNING|ERROR|CRITICAL'
  file: '{log}'
database:
  path: '{db}'
  auto_migrate: true
{security}"""


def _q(text: str) -> str:
    """A PowerShell single-quoted literal."""
    return "'" + text.replace("'", "''") + "'"


class Remote:
    """The test host: every command the harness runs on it."""

    def __init__(self, target: str, os_name: str, python: str | None):
        self.target, self.os = target, os_name
        layout = LAYOUT[os_name]
        self.win = os_name == "windows"
        self.dir, self.config = layout["dir"], layout["config"]
        if not self.win:
            _rc, home = self.sh("echo $HOME")
            self.dir = self.dir.replace("~", home.splitlines()[-1].strip(), 1)
        sep = "\\" if self.win else "/"
        self.agent = f"{self.dir}{sep}agent"
        self.log = f"{self.dir}{sep}agent.log"
        self.db = f"{self.dir}{sep}agent.db"
        self.backup = f"{self.dir}{sep}config.backup"
        self.python = self._resolve(python or layout["python"])
        self.had_config = False

    def sh(self, command: str):
        return proof._ssh(self.target, command)

    def ps(self, script: str):
        return proof._ssh(self.target, proof._ps(script))

    def _resolve(self, path: str) -> str:
        """An absolute interpreter path (root and SYSTEM have other homes)."""
        if self.win:
            rest = path[2:] if path.startswith("~\\") else None
            script = f"Join-Path $env:USERPROFILE {_q(rest)}" if rest else f"{_q(path)}"
            _rc, out = self.ps(script)
            return out.splitlines()[-1].strip() if out else path
        # Expand ~ only: realpath would follow the venv's symlink to the bare
        # interpreter, outside the venv and without the agent's dependencies.
        home = self.dir.rsplit("/", 1)[0]
        return home + path[1:] if path.startswith("~/") else path

    def stdin(self, command: str, data: bytes, timeout=600) -> int:
        result = subprocess.run(  # nosec B603 B607
            ["ssh", "-o", "BatchMode=yes", self.target, command],
            input=data,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode

    def check_python(self) -> bool:
        """The interpreter exists and has the agent's dependencies."""
        imports = "import yaml, websockets, sqlalchemy, cryptography"
        if self.win:
            rc, _out = self.ps(
                f"& {_q(self.python)} -c {_q(imports)}; exit $LASTEXITCODE"
            )
        else:
            rc, _out = self.sh(f"{self.python} -c '{imports}'")
        return rc == 0

    def hostname(self) -> str:
        _rc, out = self.sh("hostname" if self.win else "hostname -s")
        return out.splitlines()[-1].strip().split(".")[0].lower() if out else ""

    def leftover_backup(self) -> bool:
        """A backup an earlier, interrupted run never put back: it may be the
        ONLY copy of the host's real configuration."""
        if self.win:
            return (
                self.ps(f"if (-not (Test-Path {_q(self.backup)})) {{ exit 1 }}")[0] == 0
            )
        return self.sh(f"test -f {self.backup}")[0] == 0

    def ship(self, src: Path) -> bool:
        """The working tree, as a tarball over ssh (no rsync on Windows)."""
        if self.win:
            self.ps(
                f"Remove-Item -Recurse -Force {_q(self.dir)} -ErrorAction "
                f"SilentlyContinue; New-Item -ItemType Directory -Force "
                f"{_q(self.agent)} | Out-Null"
            )
            unpack = f'tar -xzf - -C "{self.agent}"'
        else:
            self.sh(f"sudo rm -rf {self.dir}")
            unpack = f"mkdir -p {self.agent} && tar -xzf - -C {self.agent}"
        excludes = [f"--exclude={pattern.rstrip('/')}" for pattern in RSYNC_EXCLUDE]
        excludes.append("--exclude=.vagrant")
        tarball = subprocess.run(  # nosec B603 B607
            ["tar", "-C", str(src), "-czf", "-", *excludes, "."],
            capture_output=True,
            check=True,
        ).stdout
        return self.stdin(unpack, tarball) == 0

    def write_config(self, text: str) -> bool:
        if self.win:
            rc, out = self.ps(
                f"if (Test-Path {_q(self.config)}) {{ Copy-Item -Force "
                f"{_q(self.config)} {_q(self.backup)}; 'had' }} else {{ 'none' }}"
            )
            self.had_config = "had" in out
            if rc != 0:
                return False
            return (
                self.stdin(
                    proof._ps(
                        "[IO.File]::WriteAllText("
                        f"{_q(self.config)}, [Console]::In.ReadToEnd())"
                    ),
                    text.encode(),
                )
                == 0
            )
        rc, out = self.sh(
            f"if [ -f {self.config} ]; then sudo cp -p {self.config} "
            f"{self.backup} && echo had; else echo none; fi"
        )
        self.had_config = "had" in out
        if rc != 0:
            return False
        return self.stdin(f"sudo tee {self.config} >/dev/null", text.encode()) == 0

    def restore_config(self) -> str:
        """Put the original back; never delete one that existed."""
        if self.win:
            script = (
                f"Copy-Item -Force {_q(self.backup)} {_q(self.config)}"
                if self.had_config
                else f"Remove-Item -Force {_q(self.config)} -ErrorAction SilentlyContinue"
            )
            rc, out = self.ps(script)
        elif self.had_config:
            rc, out = self.sh(f"sudo cp -p {self.backup} {self.config}")
        else:
            rc, out = self.sh(f"sudo rm -f {self.config}")
        if rc != 0:
            return f"COULD NOT restore {self.config} ({out}); backup: {self.backup}"
        return (
            f"restored {self.config}" if self.had_config else "removed the test config"
        )

    def start_agent(self) -> bool:
        if self.win:
            rc, _out = self.ps(
                f"$a = New-ScheduledTaskAction -Execute {_q(self.python)} "
                f"-Argument 'main.py' -WorkingDirectory {_q(self.agent)}\n"
                "$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' "
                "-LogonType ServiceAccount -RunLevel Highest\n"
                "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit "
                "([TimeSpan]::Zero) -AllowStartIfOnBatteries "
                "-DontStopIfGoingOnBatteries\n"
                f"Register-ScheduledTask -TaskName {TASK} -Action $a -Principal $p "
                "-Settings $s -Force | Out-Null\n"
                f"Start-ScheduledTask -TaskName {TASK}"
            )
            return rc == 0
        rc, _out = self.sh(
            f"sudo sh -c 'cd {self.agent} && nohup {self.python} main.py "
            f">{self.dir}/agent.out 2>&1 </dev/null & echo $! >{self.dir}/agent.pid'"
        )
        return rc == 0

    def stop_agent(self) -> None:
        if self.win:
            self.ps(
                f"Stop-ScheduledTask -TaskName {TASK} -ErrorAction SilentlyContinue\n"
                f"Unregister-ScheduledTask -TaskName {TASK} -Confirm:$false "
                "-ErrorAction SilentlyContinue\n"
                "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath "
                f"-eq {_q(self.python)} -and $_.CommandLine -match 'main.py' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
            )
            return
        pid = f"{self.dir}/agent.pid"
        self.sh(
            f"sudo sh -c 'test -f {pid} && kill $(cat {pid}) 2>/dev/null; sleep 3; "
            f"test -f {pid} && kill -9 $(cat {pid}) 2>/dev/null; true'"
        )

    def copy_identity(self, source: str) -> str | None:
        """A COPY of the host's real agent database as the test agent's, so it
        proves it is the host the server already knows (the host token is
        never rotated, so the original stays valid).  Returns its host id."""
        read = (
            "import sqlite3, sys; print(sqlite3.connect(sys.argv[1]).execute("
            "'select host_id from host_approval').fetchone()[0])"
        )
        if self.win:
            rc, out = self.ps(
                f"Copy-Item -Force {_q(source)} {_q(self.db)} -ErrorAction Stop\n"
                f"& {_q(self.python)} -c {_q(read)} {_q(self.db)}; exit $LASTEXITCODE"
            )
        else:
            rc, out = self.sh(
                f"sudo cp -p {source} {self.db} && "
                f'sudo {self.python} -c "{read}" {self.db}'
            )
        return out.splitlines()[-1].strip() if rc == 0 and out else None

    def read_log(self) -> str:
        if self.win:
            return self.ps(f"Get-Content -Raw {_q(self.log)}")[1]
        return self.sh(f"sudo cat {self.log} {self.dir}/agent.out")[1]

    def clock_view(self) -> str:
        if self.win:
            return self.ps(
                "(Get-Date).ToUniversalTime().ToString('o'); "
                "w32tm /query /status 2>&1"
            )[1]
        return self.sh("date -u; ntpq -pn 2>&1 || chronyc tracking 2>&1 || true")[1]

    def remove_dir(self) -> None:
        if self.win:
            self.ps(
                f"Remove-Item -Recurse -Force {_q(self.dir)} -ErrorAction SilentlyContinue"
            )
        else:
            self.sh(f"sudo rm -rf {self.dir}")


def _host_ids(args, token) -> set:
    status, hosts = proof._request(args.server, "GET", "/hosts", token)
    if status != 200 or not isinstance(hosts, list):
        return set()
    return {str(h.get("id")) for h in hosts}


def _new_host(args, token, hostname, known):
    _status, hosts = proof._request(args.server, "GET", "/hosts", token)
    for host in hosts if isinstance(hosts, list) else []:
        short = (host.get("fqdn") or "").split(".")[0].lower()
        if short == hostname and str(host.get("id")) not in known:
            return host
    return None


def _in_bounds(args, token, results, host, state) -> bool:
    """Measured, its time service reported -- and in bounds, resynchronized
    first if it was not (the proof starts from a clock in bounds)."""

    def fresh(clock):
        # Taken since the test agent started: an existing host carries the
        # last run's measurement and report, and judging by those queued a
        # resync the clock did not need (and the proof's own was then refused
        # as already running).
        measured = (clock.get("measured") or {}).get("measured_at") or ""
        reported_at = (clock.get("time_service") or {}).get("reported_at") or ""
        return measured >= state["started"] and reported_at >= state["started"]

    def reported():
        clock = proof._clock(args.server, token, host["id"])
        if not clock or not (clock.get("time_service") or {}).get("service"):
            return None
        if not fresh(clock):
            return None
        return clock if clock.get("status") in ("ok", "warning", "critical") else None

    clock = wait_for(results, "a measurement and the time service", reported, 900)
    if clock is None:
        log(results, "the host was never measured with its time service")
        return False
    service = clock["time_service"]["service"]
    # As found, BEFORE anything here touches it -- teardown puts it back.
    state["unit"], state["running"] = proof.find_unit(args.ssh, state["os"], service)
    log(
        results,
        f"time service {service} ({state['unit']}, "
        f"{'running' if state['running'] else 'STOPPED'}), "
        f"offset {clock['measured']['offset_ms']} ms, {clock['status']}",
    )
    if clock["status"] != "ok":
        log(results, "out of bounds to start with -- resynchronizing first")
        proof._request(args.server, "POST", f"/host/{host['id']}/clock/resync", token)

    def ok():
        clock = proof._clock(args.server, token, host["id"])
        return clock if clock and clock.get("status") == "ok" else None

    # args.timeout, not less: the agent runs one command at a time, and a
    # fresh agent's first package collection (11 minutes for winget's 4,303
    # packages on the x13s) holds a resync back until it finishes.
    clock = wait_for(results, "the clock in bounds", ok, args.timeout)
    if clock is None:
        log(results, "the host was never measured in bounds")
        return False
    if not wait_for(
        results,
        "no resync still pending",
        lambda: not proof.pending_resync(args.server, token, host["id"]),
        args.timeout,
    ):
        log(results, "a resync never finished")
        return False
    (results / "clock-before.json").write_text(json.dumps(clock, indent=2))
    return True


def bring_up(args, token, remote, results, state):
    """Ship, configure, start, register, approve.  Returns the host or None."""
    if not remote.check_python():
        log(
            results, f"no usable agent interpreter at {remote.python} (--remote-python)"
        )
        return None
    if remote.leftover_backup():
        log(
            results,
            f"{remote.backup} exists -- an earlier run did not finish. "
            f"Put it back as {remote.config} by hand, then delete it.",
        )
        return None
    log(results, f"shipping {args.agent_src} to {args.ssh}:{remote.agent}")
    if not remote.ship(args.agent_src):
        log(results, "could not ship the agent")
        return None
    host, port, https = agent_endpoint(args)
    security = ""
    if args.enrollment_token:
        security = f"security:\n  enrollment_token: '{args.enrollment_token}'\n"
    text = CONFIG.format(
        host=host, port=port, https="true" if https else "false", log=remote.log,
        db=remote.db, security=security,
    )  # fmt: skip
    if not remote.write_config(text):
        log(results, f"could not write {remote.config}")
        return None
    state["config"] = True
    known = _host_ids(args, token)
    if args.identity_db:
        host_id = remote.copy_identity(args.identity_db)
        if host_id not in known:
            log(
                results, f"{args.identity_db}: no identity the server knows ({host_id})"
            )
            return None
        state["existing"] = True
        log(results, f"running as the existing host {host_id} (a copy of its database)")
    if not remote.start_agent():
        log(results, "could not start the agent")
        return None
    state["agent"] = True
    # Naive UTC, like the server's timestamps, for _in_bounds' freshness test.
    state["started"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    log(results, f"agent started ({remote.python})")
    if state.get("existing"):
        return _existing(args, token, results, host_id, state)
    hostname = remote.hostname()
    found = wait_for(
        results, f"{hostname} to register as a new host",
        lambda: _new_host(args, token, hostname, known), args.register_timeout,
    )  # fmt: skip
    if found is None:
        log(results, "the agent never registered -- see agent.log")
        return None
    state["host"] = found
    log(results, f"registered as {found['fqdn']} ({found.get('approval_status')})")
    if found.get("approval_status") != "approved":
        status, _ = proof._request(
            args.server, "PUT", f"/host/{found['id']}/approve", token
        )
        if status != 200:
            log(results, f"approving the host failed (HTTP {status})")
            return None
        log(results, "approved")
    return found if _in_bounds(args, token, results, found, state) else None


def _existing(args, token, results, host_id, state):
    """The host the server already knows: no registration or approval -- and
    NEVER deleted at teardown, it is the machine's own record."""
    _s, hosts = proof._request(args.server, "GET", "/hosts", token)
    found = next((h for h in hosts or [] if str(h.get("id")) == host_id), None)
    if found is None:
        log(results, f"host {host_id} is not on the server")
        return None
    state["host"] = found
    log(results, f"{found['fqdn']} ({found.get('approval_status')})")
    return found if _in_bounds(args, token, results, found, state) else None


def run_proof(args, results, host) -> int:
    cmd = [
        sys.executable, str(HERE / "clock_skew_proof.py"),
        "--server", args.server, "--host-id", str(host["id"]),
        "--ssh", args.ssh, "--skew", str(args.skew), "--timeout", str(args.timeout),
    ]  # fmt: skip
    if args.expect_alert:
        cmd.append("--expect-alert")
    if args.insecure:
        cmd.append("--insecure")
    log(results, "running the proof")
    env = dict(os.environ)
    if args.token:
        env["SYSMANAGE_TOKEN"] = args.token
    proc = subprocess.run(  # nosec B603
        cmd, capture_output=True, text=True, env=env, check=False,
        timeout=args.timeout * 5,
    )  # fmt: skip
    output = proc.stdout + proc.stderr
    (results / "proof.log").write_text(output)
    print(output, flush=True)
    return proc.returncode


def collect(args, token, remote, results, state) -> None:
    host = state.get("host")
    if host is not None:
        clock = proof._clock(args.server, token, host["id"])
        (results / "clock-after.json").write_text(json.dumps(clock, indent=2))
        _s, resyncs = proof._request(
            args.server, "GET", f"/time-sync/resyncs?host_id={host['id']}", token
        )
        (results / "resyncs.json").write_text(json.dumps(resyncs, indent=2))
    if state.get("agent"):
        (results / "agent.log").write_text(remote.read_log())
    (results / "host-clock.txt").write_text(remote.clock_view())


def tear_down(args, token, remote, results, state) -> None:
    if args.keep:
        log(results, f"--keep: leaving the agent, {remote.dir} and the host")
        return
    if state.get("agent"):
        remote.stop_agent()
        log(results, "stopped the test agent")
    host = state.get("host")
    if host is not None and state.get("existing"):
        log(results, f"kept {host['fqdn']} on the server (the machine's own host)")
    elif host is not None:
        status, _ = proof._request(args.server, "DELETE", f"/host/{host['id']}", token)
        log(results, f"deleted the host from the server (HTTP {status})")
    restored = True
    if state.get("config"):
        message = remote.restore_config()
        restored = not message.startswith("COULD NOT")
        log(results, message)
    if state.get("unit"):
        ok = proof.set_service(args.ssh, remote.os, state["unit"], state["running"])
        want = "running" if state["running"] else "stopped"
        log(
            results,
            (
                f"{state['unit']} {want}, as found"
                if ok
                else f"COULD NOT put {state['unit']} back ({want}) -- do it by hand"
            ),
        )
    if restored:
        remote.remove_dir()
        log(results, f"removed {remote.dir}")
    else:
        log(results, f"KEPT {remote.dir}: it holds the only copy of the config")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", required=True, help="the API URL")
    parser.add_argument("--ssh", required=True, help="the test host, e.g. freebsd")
    parser.add_argument("--agent-server", help="host:port the AGENT connects to")
    parser.add_argument("--agent-https", action="store_true")
    parser.add_argument("--enrollment-token", help="for a multi-tenant server")
    parser.add_argument("--agent-src", type=Path, default=DEFAULT_AGENT_SRC)
    parser.add_argument(
        "--remote-python",
        help="the host's agent interpreter (default: ~/dev/sysmanage-agent/.venv)",
    )
    parser.add_argument(
        "--identity-db",
        help="the host's real agent database (a path ON the host): a copy makes "
        "the test agent the host the server already knows, instead of a new one",
    )
    parser.add_argument(
        "--expect-alert",
        action="store_true",
        help="also assert a clock_offset alert opens and resolves itself",
    )
    parser.add_argument("--skew", type=float, default=120.0)
    # Longer than the VM's: a real machine's first package collection can hold
    # the agent's command queue for many minutes (see _in_bounds).
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--register-timeout", type=int, default=600)
    parser.add_argument("--results", type=Path, default=Path("clock-skew-results"))
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--token", default=os.environ.get("SYSMANAGE_TOKEN"))
    parser.add_argument("--insecure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.server.lower().startswith(("https://", "http://")):
        sys.exit("--server must be an http:// or https:// URL.")
    if not proof._SSH_TARGET.match(args.ssh):
        sys.exit("--ssh must be user@host or host.")
    if not (args.agent_src / "main.py").is_file():
        sys.exit(f"--agent-src: no agent at {args.agent_src}")
    os_name = proof.remote_os(args.ssh)
    if os_name not in LAYOUT:
        sys.exit(
            f"{args.ssh}: {os_name or 'unreachable'} -- FreeBSD or Windows only "
            "(Linux: clock_skew_vm_test.py)."
        )
    if args.insecure:
        # nosemgrep
        proof._CONTEXT = proof.ssl._create_unverified_context()  # nosec B323
    token = args.token or proof._login(args.server)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = (args.results / f"{stamp}-{args.ssh}").resolve()
    results.mkdir(parents=True)
    remote = Remote(args.ssh, os_name, args.remote_python)
    log(results, f"{args.ssh}: {os_name}, agent interpreter {remote.python}")

    state = {"os": os_name}
    code, reason = 2, "the harness stopped before the proof ran"
    try:
        host = bring_up(args, token, remote, results, state)
        if host is not None:
            code = run_proof(args, results, host)
            reason = {0: "PROVEN", 1: "NOT PROVEN"}.get(code, f"proof exited {code}")
    except KeyboardInterrupt:
        reason = "interrupted"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        reason = f"harness error: {exc}"
        log(results, reason)
    finally:
        try:
            collect(args, token, remote, results, state)
        finally:
            tear_down(args, token, remote, results, state)
    summary = (
        f"Clock skew proof -- {stamp}\n"
        f"result:    {reason}\n"
        f"server:    {args.server}\n"
        f"host:      {args.ssh} ({os_name})\n"
        f"skew:      +{args.skew:g} s\n"
        f"alert:     {args.expect_alert}\n"
        f"artifacts: {results}\n"
    )
    (results / "SUMMARY.txt").write_text(summary)
    print("\n" + summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
