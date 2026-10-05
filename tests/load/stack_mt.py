# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The load stack in multi-tenant mode (Phase 22 exit criteria: "across many
tenants").

Everything ``stack.py`` builds, plus what a multi-tenant server needs -- all
of it throwaway and none of it shared with the developer's real stack:

  * OpenBAO in dev mode in a container (host network, so its database
    secrets engine reaches the PostgreSQL container's published port);
  * a self-signed ``multitenant_saas`` license and the ``multitenancy_engine``
    bundle from the Pro+ tree, registered in the module cache -- offline, the
    license server never called (``phone_home_url: ""``), the key cached in
    this stack's own directory (``license.public_key_path``);
  * the provisioner bootstrap (``scripts/provision_bootstrap.py``), a database
    admin (the control plane needs a real user with Manage Tenants), then N
    tenants created, auto-provisioned (own database, OpenBAO role, tenant
    migrations) and given an enrollment token each.

The tenants, their databases and their tokens are saved in the stack state:
the fleet enrolls agents round-robin across the tokens, and the observer and
the approval step visit every tenant database.

Needs: docker, the Pro+ repo (``SYSMANAGE_PROPLUS_DIR``, default a sibling
checkout) with a built ``multitenancy_engine`` bundle, and the docs repo's
``screenshots/pro_keygen.py`` (``SYSMANAGE_DOCS_DIR``).
"""

# stack_mt extends stack.py and uses its internals by design.
# pylint: disable=protected-access

import json
import os
import platform
import secrets
import shutil
import signal
import subprocess  # nosec B404 - fixed argv lists, no shell
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from tests.load import stack

BAO_IMAGE = "openbao/openbao:2.5.4"
BAO_CONTAINER = f"sysmanage-load-bao{stack._SUFFIX}"  # pylint: disable=protected-access
BAO_PORT = 58200 + stack.INSTANCE
PROPLUS_DIR = Path(os.environ.get("SYSMANAGE_PROPLUS_DIR",
                                  stack.REPO.parent / "sysmanage-professional-plus"))  # fmt: skip
DOCS_DIR = Path(
    os.environ.get("SYSMANAGE_DOCS_DIR", stack.REPO.parent / "sysmanage-docs")
)
ENGINE = "multitenancy_engine"
MT_MAX_CONNECTIONS = 3000
ADMIN = "load-tenant-admin@sysmanage.org"


BAO_PID_FILE = stack.STATE_DIR / "bao.pid"


def _bao_stop_native() -> None:
    try:
        pid = int(BAO_PID_FILE.read_text(encoding="utf-8"))
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    BAO_PID_FILE.unlink(missing_ok=True)


def _bao_up(token: str) -> str:
    args = ["server", "-dev", f"-dev-root-token-id={token}",
            f"-dev-listen-address=127.0.0.1:{BAO_PORT}"]  # fmt: skip
    if stack.native():  # the `bao` binary itself (OpenBSD has no docker)
        _bao_stop_native()
        with open(stack.STATE_DIR / "bao.log", "ab") as log:
            proc = subprocess.Popen(  # nosec B603 B607 # pylint: disable=consider-using-with
                ["bao", *args], stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True,
            )  # fmt: skip
        BAO_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    else:
        subprocess.run(["docker", "rm", "-f", BAO_CONTAINER], check=False,  # nosec B603 B607
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
        stack._run([  # pylint: disable=protected-access
            "docker", "run", "-d", "--name", BAO_CONTAINER, "--network", "host",
            "-e", "SKIP_SETCAP=1", BAO_IMAGE, *args,
        ], stdout=subprocess.DEVNULL)  # fmt: skip
    url = f"http://127.0.0.1:{BAO_PORT}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"{url}/v1/sys/health", timeout=2
            ):  # nosec B310
                return url
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise SystemExit("OpenBAO container did not become ready")


def _license(out: Path) -> str:
    """A self-signed multitenant_saas license; its public key lands in ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    keygen = DOCS_DIR / "screenshots" / "pro_keygen.py"
    env = dict(
        os.environ,
        TIER="multitenant_saas",
        PRO_PLUS_DIR=str(PROPLUS_DIR),
        OUT_DIR=str(out),
    )
    stack._run([sys.executable, str(keygen)], env=env,  # pylint: disable=protected-access
               cwd=PROPLUS_DIR, stdout=subprocess.DEVNULL)  # fmt: skip
    return (out / "license.jwt").read_text(encoding="utf-8").strip()


def _engine_bundle() -> Path:
    root = PROPLUS_DIR / "storage" / "modules" / ENGINE
    plat = platform.system().lower()
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(
        platform.machine().lower(), platform.machine().lower()
    )
    bundles = sorted(root.glob(f"*/{plat}/{arch}/abi3/*.tar.gz"),
                     key=lambda p: [int(x) for x in p.parts[-5].split(".")])  # fmt: skip
    if not bundles:
        raise SystemExit(
            f"no built {ENGINE} bundle under {root} -- build the engine first"
        )
    return bundles[-1]


def _install_engine(modules: Path) -> Path:
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
    dest = modules / f"{ENGINE}_{pyver}"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    with tarfile.open(_engine_bundle(), "r:gz") as tar:
        tar.extractall(dest, filter="data")
    return dest


_REGISTER = r"""
import hashlib, json, platform, sys
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from backend.persistence import db
from backend.persistence.models import ProPlusModuleCache
d = Path(sys.argv[1]); code, pyv = sys.argv[2], sys.argv[3]
so = sorted(d.glob("*.so"))[0]
h = hashlib.sha512(so.read_bytes()).hexdigest()
ver = json.loads((d / "metadata.json").read_text())["version"]
plat = platform.system().lower()
arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
with sessionmaker(bind=db.get_engine())() as s:
    s.query(ProPlusModuleCache).filter_by(module_code=code, platform=plat, architecture=arch,
                                          python_version=pyv).delete()
    s.add(ProPlusModuleCache(module_code=code, version=ver, platform=plat, architecture=arch,
                             python_version=pyv, file_path=str(so), file_hash=h,
                             downloaded_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    s.commit()
"""

_ADMIN = r"""
import sys
sys.path.insert(0, ".")
from scripts._sysmanage_secure_installation import create_admin_user
create_admin_user({"email": sys.argv[1], "password": sys.argv[2], "first_name": "Load",
                   "last_name": "Admin"}, salt=None)
"""


def mt_config(
    base: dict, bao_url: str, bao_token: str, license_key: str, state_dir: Path
) -> dict:
    """``stack._config`` turned multi-tenant."""
    cfg = dict(base)
    cfg["multitenancy"] = {"enabled": True, "self_service_provisioning": True}
    cfg["vault"] = {"enabled": True, "url": bao_url, "token": bao_token, "mount_path": "secret",
                    "database_mount_path": "database", "verify_ssl": False}  # fmt: skip
    cfg["license"] = {"key": license_key, "modules_path": str(state_dir / "modules"),
                      "phone_home_url": "",
                      "public_key_path": str(state_dir / "license" / "public_key.pem")}  # fmt: skip
    return cfg


def _api(port, method, path, token=None, body=None, timeout=300):
    req = urllib.request.Request(  # nosec B310 - fixed local URL
        f"http://127.0.0.1:{port}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )  # fmt: skip
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return json.loads(resp.read() or b"{}")


def make_tenants(port, password, count, db_url_base) -> list:
    """Create, provision and token ``count`` tenants; returns their records."""
    token = _api(
        port, "POST", "/api/v1/login", body={"userid": ADMIN, "password": password}
    )
    jwt = token.get("Authorization") or token.get("access_token")
    tenants = []
    for i in range(count):
        slug = f"load{i:03d}"
        tenant = _api(port, "POST", "/api/v1/control-plane/tenants", jwt,
                      {"name": f"Load tenant {i}", "slug": slug, "edition": "enterprise"})  # fmt: skip
        placed = _api(port, "POST", f"/api/v1/control-plane/tenants/{tenant['id']}/auto-provision",
                      jwt, {"host": "127.0.0.1", "port": stack.PG_PORT, "region": "load",
                            "tier": "silo"})  # fmt: skip
        enroll = _api(port, "POST", f"/api/v1/control-plane/tenants/{tenant['id']}/enrollment-tokens",
                      jwt, {"label": "load fleet", "expires_in_days": 30,
                            "max_uses": 1_000_000})  # fmt: skip
        tenants.append({"id": tenant["id"], "slug": slug, "token": enroll["token"],
                        "db_url": f"{db_url_base}/{placed['dbname']}"})  # fmt: skip
        print(f"  tenant {slug}: database {placed['dbname']}", flush=True)
    return tenants


def up_mt(port: int, tenants: int, bind_host: str = "127.0.0.1") -> dict:
    """Bring up a multi-tenant load stack with ``tenants`` tenants."""
    import yaml  # pylint: disable=import-outside-toplevel

    state_dir = stack.STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    stack.fresh_server_log()
    password = secrets.token_urlsafe(16)
    # Sized for the pools a 20-tenant server plans (workers x (bootstrap +
    # tenants x 8)): at 500 the startup fit had to give each tenant database
    # one connection per worker, and the run measured that, not the server
    # (2026-10-05).  The server's own fit keeps it honest at any size.
    if stack.native():
        stack._start_postgres_native(
            password, MT_MAX_CONNECTIONS
        )  # pylint: disable=protected-access
    else:
        stack._start_postgres(
            password, MT_MAX_CONNECTIONS
        )  # pylint: disable=protected-access
    db = {"user": stack.PG_USER, "password": password, "host": "127.0.0.1",
          "port": stack.PG_PORT, "name": stack.PG_DB}  # fmt: skip
    bao_token = secrets.token_urlsafe(24)
    print("starting OpenBAO (dev mode) ...", flush=True)
    bao_url = _bao_up(bao_token)
    print("self-signing a multitenant_saas license ...", flush=True)
    license_key = _license(state_dir / "license")
    engine_dir = _install_engine(state_dir / "modules")
    cfg = mt_config(stack._config(port, db, bind_host), bao_url, bao_token,  # pylint: disable=protected-access
                    license_key, state_dir)  # fmt: skip
    config_path = state_dir / "sysmanage-load.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    config_path.chmod(0o600)
    code = stack.pin_code()
    env = stack._server_env(
        config_path, code, multitenancy=True
    )  # pylint: disable=protected-access
    print("migrating the registry / shared / tenant chains ...", flush=True)
    stack._run([sys.executable, "scripts/sysmanage_migrate.py", "--no-tenants"],  # pylint: disable=protected-access
               cwd=code, env=env, stdout=subprocess.DEVNULL)  # fmt: skip
    pyver = engine_dir.name.rsplit("_", 1)[1]
    stack._run([sys.executable, "-c", _REGISTER, str(engine_dir), ENGINE, pyver],  # pylint: disable=protected-access
               cwd=code, env=env, stdout=subprocess.DEVNULL)  # fmt: skip
    admin_password = "Load-" + secrets.token_urlsafe(12)
    stack._run([sys.executable, "-c", _ADMIN, ADMIN, admin_password], cwd=code,  # pylint: disable=protected-access
               env=env, stdout=subprocess.DEVNULL)  # fmt: skip
    print("provisioner bootstrap ...", flush=True)
    stack._run([sys.executable, "scripts/provision_bootstrap.py", "--bao-addr", bao_url,  # pylint: disable=protected-access
                "--bao-token", bao_token, "--pg-host", "127.0.0.1",
                "--pg-port", str(stack.PG_PORT), "--pg-db", stack.PG_DB,
                "--pg-superuser", stack.PG_USER, "--pg-superuser-password", password],
               cwd=code, env=env, stdout=subprocess.DEVNULL)  # fmt: skip
    base_url = f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}"
    state = {"port": port, "config": str(config_path), "code": str(code),
             "db_url": f"{base_url}/{db['name']}", "container": True, "server_pid": None,
             "multitenancy": True, "bao_container": BAO_CONTAINER,
             "bind_host": bind_host}  # fmt: skip
    stack._save(state)  # pylint: disable=protected-access
    stack.start_server(state)
    print(f"creating {tenants} tenant(s) ...", flush=True)
    state["tenants"] = make_tenants(port, admin_password, tenants, base_url)
    stack._save(state)  # pylint: disable=protected-access
    print(f"multi-tenant load stack up: {tenants} tenants on http://127.0.0.1:{port}")
    return state


def down_mt() -> None:
    if stack.native():
        _bao_stop_native()
        return
    subprocess.run(["docker", "rm", "-f", BAO_CONTAINER], check=False,  # nosec B603 B607
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
