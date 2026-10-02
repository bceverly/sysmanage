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
import shutil
import signal
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


def _start_postgres(password):
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
            "--tmpfs", "/var/lib/postgresql/data",
            PG_IMAGE, "-c", "max_connections=500",
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


def _container_exists():
    out = subprocess.run(  # nosec B603 B607 - fixed argv
        ["docker", "ps", "-aq", "-f", f"name=^{CONTAINER}$"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return bool(out.stdout.strip())


def _config(port, db):
    """A complete standalone config -- nothing inherited from this box."""
    return {
        "api": {"host": "127.0.0.1", "port": port, "certFile": "", "keyFile": "", "chainFile": ""},
        "database": db,
        "security": {
            "password_salt": secrets.token_hex(32),
            "admin_userid": "load-admin@sysmanage.org",  # .test is refused as an email domain
            "admin_password": "Load-" + secrets.token_urlsafe(12),
            "jwt_secret": secrets.token_urlsafe(48),
            "jwt_algorithm": "HS256",
            "jwt_auth_timeout": 6000,
            "jwt_refresh_timeout": 60000,
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


def _server_env(config_path, code=REPO):
    env = dict(os.environ)
    env.update(
        SYSMANAGE_CONFIG_PATH=str(config_path),
        SYSMANAGE_MULTITENANCY="false",
        SYSMANAGE_DISABLE_EMAIL="true",
        OTEL_ENABLED="false",
        PYTHONPATH=str(code),
    )
    return env


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


def start_server(state):
    """Start the server; returns its pid.  The log is appended to, so a
    restart's output follows the previous run's."""
    # The child keeps its own copy of the log descriptor, so ours can close.
    # The server outlives this call on purpose: no `with` for the Popen.
    with open(STATE_DIR / "server.log", "ab") as log:
        proc = subprocess.Popen(  # nosec B603 # pylint: disable=consider-using-with
            [sys.executable, "-m", "backend.main"],
            cwd=_code(state), env=_server_env(state["config"], _code(state)),
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


def up(port, db_url, pin=True):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if db_url:
        from urllib.parse import urlparse  # pylint: disable=import-outside-toplevel

        parsed = urlparse(db_url)
        db = {"user": parsed.username, "password": parsed.password, "host": parsed.hostname,
              "port": parsed.port or 5432, "name": parsed.path.lstrip("/")}  # fmt: skip
        container = False
    else:
        if not shutil.which("docker"):
            raise SystemExit(
                "docker is required (or pass --db-url for an existing database)"
            )
        password = secrets.token_urlsafe(16)
        _start_postgres(password)
        db = {"user": PG_USER, "password": password, "host": "127.0.0.1",
              "port": PG_PORT, "name": PG_DB}  # fmt: skip
        container = True
    config_path = STATE_DIR / "sysmanage-load.yaml"
    import yaml  # pylint: disable=import-outside-toplevel

    config_path.write_text(yaml.safe_dump(_config(port, db)), encoding="utf-8")
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
    container and on an external database (CI) alike."""
    state = load_state()
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
    if state.get("container"):
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
    args = parser.parse_args()
    if args.action == "up":
        up(args.port, args.db_url, pin=not args.no_pin)
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
