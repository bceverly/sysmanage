# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A disposable SysManage server for fleet load tests (Phase 22).

The fleet scenarios have to restart the server mid-run (that is the storm
they measure) and read its queue tables, so they need a server they own --
never the developer's real stack, its database or its OpenBAO.  This module
builds one:

  * PostgreSQL in a throwaway container on tmpfs (or an external database
    via --db-url, which is what CI's service container uses);
  * a standalone config written from scratch -- it never reads
    /etc/sysmanage.yaml -- with single-tenant mode, no vault, no email;
  * migrations through scripts/sysmanage_migrate.py, the operators' tool;
  * the server on its own port, started, stopped and restarted on demand.

Usage:
    python tests/load/stack.py up      [--port 18080] [--db-url URL]
    python tests/load/stack.py restart
    python tests/load/stack.py reset     # empty database, re-migrated
    python tests/load/stack.py repin     # take a fresh copy of the code, then reset
    python tests/load/stack.py down
"""

import argparse
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess  # nosec B404 - fixed argv lists, no shell
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Independent stacks side by side (e.g. a security check while a long load
# run holds instance 0): SYSMANAGE_LOAD_INSTANCE=N moves the state directory,
# container and ports.  Instance 0 keeps the original names.
INSTANCE = int(os.environ.get("SYSMANAGE_LOAD_INSTANCE", "0"))
_SUFFIX = f"-{INSTANCE}" if INSTANCE else ""
STATE_DIR = REPO / ".runtime-logs" / f"load{_SUFFIX}"
STATE_FILE = STATE_DIR / "stack.json"
CONTAINER = f"sysmanage-load-pg{_SUFFIX}"
PG_IMAGE = "postgres:16"
PG_PORT = 55432 + INSTANCE
# What the server needs to run, copied at `up` so a long run measures ONE
# version of the code: editing the working tree mid-run must not change what
# the next reset starts (it did, 2026-10-01 -- half a baseline ladder ran on
# code changed during it).  `repin` takes a fresh copy on purpose.
CODE_PARTS = ("backend", "alembic", "scripts", "config", "alembic.ini")
PG_USER = "sysmanage"
PG_DB = "sysmanage_load"


def _run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)  # nosec B603 - fixed argv


def _save(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_state():
    """The running stack's description, as `up` wrote it."""
    if not STATE_FILE.exists():
        raise SystemExit("no load stack is up -- run: python tests/load/stack.py up")
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _start_postgres(password, max_connections=500):
    if _container_exists():
        _run(["docker", "rm", "-f", CONTAINER], stdout=subprocess.DEVNULL,
             stderr=subprocess.DEVNULL)  # fmt: skip
    _run(
        [
            "docker", "run", "-d", "--name", CONTAINER,
            "-e", f"POSTGRES_USER={PG_USER}",
            "-e", f"POSTGRES_PASSWORD={password}",
            "-e", f"POSTGRES_DB={PG_DB}",
            "-p", f"127.0.0.1:{PG_PORT}:5432",
            "--tmpfs", "/var/lib/postgresql/data", "--shm-size", "1g",
            PG_IMAGE, "-c", f"max_connections={max_connections}",
            # Per-statement cost for the observer's report (observe.py).
            "-c", "shared_preload_libraries=pg_stat_statements",
        ],
        stdout=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(60):
        ready = subprocess.run(  # nosec B603 B607 - fixed argv
            ["docker", "exec", CONTAINER, "pg_isready", "-U", PG_USER, "-d", PG_DB],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )  # fmt: skip
        if ready.returncode == 0:
            # pg_isready answers before the init scripts finish; give the
            # final restart a moment.
            time.sleep(2)
            return
        time.sleep(1)
    raise SystemExit("PostgreSQL container did not become ready")


# Native mode (no docker, e.g. OpenBSD): a throwaway PostgreSQL cluster in the
# state directory instead of the container.  fsync is off -- the container
# ran on tmpfs, and runs must stay comparable; it lives only for the run.
PGDATA = STATE_DIR / "pgdata"


def native() -> bool:
    """True when the stack runs its services as processes, not containers."""
    return os.environ.get("LOAD_NATIVE") == "1" or not shutil.which("docker")


def _pg_stat_statements_available() -> bool:
    try:
        libdir = subprocess.run(  # nosec B603 B607 - fixed argv
            ["pg_config", "--pkglibdir"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    return any(Path(libdir).glob("pg_stat_statements.*"))


def _stop_postgres_native():
    if (PGDATA / "postmaster.pid").exists():
        subprocess.run(  # nosec B603 B607 - fixed argv
            ["pg_ctl", "-D", str(PGDATA), "-m", "fast", "-w", "stop"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )  # fmt: skip
    shutil.rmtree(PGDATA, ignore_errors=True)


def _start_postgres_native(password, max_connections=500):
    _stop_postgres_native()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pwfile = STATE_DIR / "pg-password"
    pwfile.write_text(password, encoding="utf-8")
    pwfile.chmod(0o600)
    try:
        _run(["initdb", "-D", str(PGDATA), "-U", PG_USER, f"--pwfile={pwfile}",
              "--auth-local=trust", "--auth-host=scram-sha-256", "-E", "UTF8"],
             stdout=subprocess.DEVNULL)  # fmt: skip
    finally:
        pwfile.unlink()
    options = [
        f"-p {PG_PORT}", "-c listen_addresses=127.0.0.1",
        f"-c unix_socket_directories={STATE_DIR}", f"-c max_connections={max_connections}",
        "-c fsync=off", "-c synchronous_commit=off", "-c full_page_writes=off",
    ]  # fmt: skip
    if _pg_stat_statements_available():
        options.append("-c shared_preload_libraries=pg_stat_statements")
    else:
        print("  (pg_stat_statements not installed: no per-statement report)")
    _run(["pg_ctl", "-D", str(PGDATA), "-l", str(STATE_DIR / "postgres.log"),
          "-w", "-t", "60", "-o", " ".join(options), "start"],
         stdout=subprocess.DEVNULL)  # fmt: skip
    _run(["createdb", "-h", str(STATE_DIR), "-p", str(PG_PORT), "-U", PG_USER, PG_DB])


def _container_exists():
    out = subprocess.run(  # nosec B603 B607 - fixed argv
        ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER}$"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return bool(out.stdout.strip())


def _config(port, db, bind_host="127.0.0.1"):
    """A complete standalone config -- nothing inherited from this box."""
    return {
        "api": {"host": bind_host, "port": port, "certFile": "", "keyFile": "", "chainFile": "",
                # --bind-host 0.0.0.0 is deliberate (a fleet on another
                # machine); unacknowledged, the server binds loopback.
                "allow_public_bind": bind_host in ("0.0.0.0", "::")},
        "database": db,
        "security": {
            "password_salt": secrets.token_hex(32),
            "admin_userid": "load-admin@sysmanage.org",  # .test is refused as an email domain
            "admin_password": "Load-" + secrets.token_urlsafe(12),
            "jwt_secret": secrets.token_urlsafe(48),
            "jwt_algorithm": "HS256",
            "jwt_auth_timeout": 6000,
            "jwt_refresh_timeout": 60000,
            # A remote load machine puts every agent behind ONE address (the
            # large-NAT case); unregistered agents are counted per address,
            # so a whole fleet enrolling at once needs the allowance a real
            # site that size would configure.
            "agent_connection_limits": {"per_address": 1000000},
        },
        "webui": {"host": "127.0.0.1", "port": 3999},
        # WARNING keeps a 10k-agent run from writing gigabytes of INFO lines;
        # the measurements come from the database and the agents, not the log.
        "logging": {"level": "WARNING"},
        "message_queue": {"expiration_timeout_minutes": 60, "cleanup_interval_minutes": 30},
        "multitenancy": {"enabled": False},
        "vault": {"enabled": False},
        "email": {"enabled": False},
        # Port 0: any free UDP port, so this server can run beside a real one
        # (the beacon's bind failure aborts startup).
        "discovery": {"port": 0},
    }  # fmt: skip


def _server_env(config_path, code=REPO, multitenancy=False):
    env = dict(os.environ)
    env.update(
        SYSMANAGE_CONFIG_PATH=str(config_path),
        SYSMANAGE_MULTITENANCY="true" if multitenancy else "false",
        SYSMANAGE_DISABLE_EMAIL="true",
        OTEL_ENABLED="false",
        PYTHONPATH=str(code),
    )
    return env


def fresh_server_log():
    """A new stack starts a new server.log (restarts within it append).  It
    grew to 25 GB appending across every run; the previous one is kept."""
    log = STATE_DIR / "server.log"
    if log.exists():
        log.replace(STATE_DIR / "server.log.prev")


def pin_code():
    """Copy the code under test into the stack's state directory."""
    dest = STATE_DIR / "code"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for part in CODE_PARTS:
        src = REPO / part
        if src.is_dir():
            shutil.copytree(
                src, dest / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
            )
        elif src.exists():
            shutil.copy2(src, dest / part)
    return dest


def _code(state):
    return Path(state.get("code") or REPO)


def _wait_healthy(port, timeout=120):
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                url, timeout=2
            ) as resp:  # nosec B310 - fixed local URL
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            # Not up yet: retry until the deadline.
            time.sleep(1)
            continue
        time.sleep(1)
    raise SystemExit(
        f"server on port {port} did not become healthy; see {STATE_DIR}/server.log"
    )


def _port_taken(port) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _server_prefix():
    """``LOAD_SERVER_PREFIX``: a command the server runs under, e.g. a
    profiler (``py-spy record ... --``).  It must start the server as its
    child: ptrace_scope=1 lets a profiler trace only its own children."""
    return shlex.split(os.environ.get("LOAD_SERVER_PREFIX", ""))


def start_server(state):
    """Start the server; returns its pid.  The log is appended to, so a
    restart's output follows the previous run's."""
    # Something already answering on the port would pass the health check
    # and take the fleet's traffic while ours fails to bind -- orphaned
    # workers of an earlier server did exactly that, twice (2026-10-02), and
    # the runs measured a server on a database that no longer existed.
    if _port_taken(state["port"]):
        raise SystemExit(
            f"port {state['port']} is already in use (an earlier server's orphaned "
            f"workers?); find them with: ss -ltnp | grep :{state['port']}"
        )
    # The child keeps its own copy of the log descriptor, so ours can close.
    # The server outlives this call on purpose: no `with` for the Popen.
    with open(STATE_DIR / "server.log", "ab") as log:
        proc = subprocess.Popen(  # nosec B603 # pylint: disable=consider-using-with
            _server_prefix() + [sys.executable, "-m", "backend.main"],
            cwd=_code(state),
            env=_server_env(state["config"], _code(state), state.get("multitenancy", False)),
            stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
    state["server_pid"] = proc.pid
    _save(state)
    _wait_healthy(state["port"])
    return proc.pid


def _alive(pid):
    """True while ``pid`` runs.  Reaps it first when it is our own child (a
    restart from the harness), or a zombie would look alive forever."""
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False
    except ChildProcessError:
        pass  # not our child (started by an earlier `stack.py up`)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def stop_server(state, grace=20):
    """Stop the server (SIGTERM, then SIGKILL after ``grace`` seconds)."""
    pid = state.get("server_pid")
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        state["server_pid"] = None
        _save(state)
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _alive(pid):
            break
        time.sleep(0.5)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            # It finished exiting on its own between the check and the kill.
            pid = None
    state["server_pid"] = None
    _save(state)


def restart_server(state, down_seconds=0):
    """Stop the server, stay down ``down_seconds``, start it again."""
    stop_server(state)
    time.sleep(down_seconds)
    return start_server(state)


def up(port, db_url, pin=True, bind_host="127.0.0.1"):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fresh_server_log()
    if db_url:
        from urllib.parse import urlparse  # pylint: disable=import-outside-toplevel

        parsed = urlparse(db_url)
        db = {"user": parsed.username, "password": parsed.password, "host": parsed.hostname,
              "port": parsed.port or 5432, "name": parsed.path.lstrip("/")}  # fmt: skip
        container = False
    else:
        password = secrets.token_urlsafe(16)
        if native():
            _start_postgres_native(password)
        else:
            _start_postgres(password)
        db = {"user": PG_USER, "password": password, "host": "127.0.0.1",
              "port": PG_PORT, "name": PG_DB}  # fmt: skip
        container = True
    config_path = STATE_DIR / "sysmanage-load.yaml"
    import yaml  # pylint: disable=import-outside-toplevel

    config_path.write_text(
        yaml.safe_dump(_config(port, db, bind_host)), encoding="utf-8"
    )
    config_path.chmod(0o600)
    code = pin_code() if pin else REPO
    print(f"migrating the load database (code under test: {code}) ...")
    _run([sys.executable, "scripts/sysmanage_migrate.py"], cwd=code,
         env=_server_env(config_path, code), stdout=subprocess.DEVNULL)  # fmt: skip
    state = {
        "port": port,
        "config": str(config_path),
        "code": str(code),
        "db_url": f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['name']}",
        "container": container,
        "server_pid": None,
    }
    _save(state)
    pid = start_server(state)
    print(f"load stack up: server pid {pid} on http://127.0.0.1:{port}")


def reset():
    """Stop the server, empty the database, migrate, start again: every
    scenario starts from the same clean state.  Works on the throwaway
    container and on an external database (CI) alike.  A multi-tenant stack
    is rebuilt from scratch (its tenants have databases and OpenBAO roles
    of their own)."""
    state = load_state()
    if state.get("multitenancy"):
        from tests.load import stack_mt  # pylint: disable=import-outside-toplevel

        stop_server(state)
        state = stack_mt.up_mt(state["port"], len(state.get("tenants") or []),
                               state.get("bind_host", "127.0.0.1"))  # fmt: skip
        return state["server_pid"]
    stop_server(state)
    from sqlalchemy import (
        create_engine,
        text,
    )  # pylint: disable=import-outside-toplevel

    engine = create_engine(
        state["db_url"].replace("postgresql://", "postgresql+psycopg://", 1)
    )
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()
    _run([sys.executable, "scripts/sysmanage_migrate.py"], cwd=_code(state),
         env=_server_env(state["config"], _code(state)), stdout=subprocess.DEVNULL)  # fmt: skip
    return start_server(state)


def down():
    if not STATE_FILE.exists():
        return
    state = load_state()
    stop_server(state)
    if state.get("bao_container"):
        from tests.load import stack_mt  # pylint: disable=import-outside-toplevel

        stack_mt.down_mt()
    if state.get("container") and native():
        _stop_postgres_native()
    elif state.get("container"):
        subprocess.run(  # nosec B603 B607 - fixed argv
            ["docker", "rm", "-f", CONTAINER],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )  # fmt: skip
    STATE_FILE.unlink()
    print("load stack down")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("action", choices=["up", "down", "restart", "reset", "repin"])
    parser.add_argument("--no-pin", action="store_true",
                        help="run the working tree itself instead of a copy taken at `up`")  # fmt: skip
    parser.add_argument("--port", type=int, default=18080 + INSTANCE)
    parser.add_argument("--db-url", default=None,
                        help="use this PostgreSQL instead of a throwaway container")  # fmt: skip
    parser.add_argument("--bind-host", default="127.0.0.1",
                        help="0.0.0.0 when the fleet runs on another machine (--remote-fleet)")  # fmt: skip
    parser.add_argument("--tenants", type=int, default=0,
                        help="multi-tenant mode with this many tenants (stack_mt.py)")  # fmt: skip
    args = parser.parse_args()
    if args.action == "up" and args.tenants:
        from tests.load import stack_mt  # pylint: disable=import-outside-toplevel

        stack_mt.up_mt(args.port, args.tenants, args.bind_host)
    elif args.action == "up":
        up(args.port, args.db_url, pin=not args.no_pin, bind_host=args.bind_host)
    elif args.action == "repin":
        state = load_state()
        state["code"] = str(pin_code())
        _save(state)
        print(f"code re-pinned; server pid {reset()}")
    elif args.action == "down":
        down()
    elif args.action == "reset":
        print(f"stack reset, server pid {reset()}")
    else:
        print(f"server restarted, pid {restart_server(load_state())}")


if __name__ == "__main__":
    main()
