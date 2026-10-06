# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""A license-server publish leaves no customer without engines (Phase 22.4
exit criterion).

Before 22.4 an engine update unloaded and deleted the working engine BEFORE
downloading its replacement, so a license server overloaded by a publish
left customers with no engine until the next cycle (up to 6 hours).  This
scenario publishes a new engine version to a fleet of simulated customer
servers while the license server misbehaves the way it does after a
publish, and watches every customer the whole time:

  1. two versions of a small compiled test engine are built (Cython);
  2. a fake license server (aiohttp, the real /api/v1/modules/versions and
     /download protocol) publishes 1.0.0; customers -- each a process of its
     own running the real ``ModuleLoader.update_modules`` with its own
     database and modules directory (publish_customer.py) -- install it;
  3. 1.0.1 is published under CHAOS for ``--chaos-seconds``: a share of
     downloads answer 503, some stall, some arrive corrupted, and for the
     first part the download still serves the OLD bundle while the versions
     call already names the new one (a CDN not yet caught up);
  4. the chaos ends and the customers converge.

Criteria: no customer is ever without its engine (loaded, and its cached
file on disk) once it has one; every customer ends on 1.0.1; and the chaos
was real -- downloads did fail during it (the positive control: a run where
nothing failed proves nothing).

Usage: python tests/load/publish_scenario.py --customers 40 --output-json r.json
"""

import argparse
import asyncio
import hashlib
import io
import json
import os
import random
import shutil
import subprocess  # nosec B404 - fixed argv
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Dict

import yaml
from aiohttp import web

REPO = Path(__file__).resolve().parents[2]
CODE = "loadtest_engine"
OLD, NEW = "1.0.0", "1.0.1"


def build_engine(workdir: Path, version: str) -> bytes:
    """A compiled engine reporting ``version``, as a release bundle (.tar.gz
    of the .so and metadata.json)."""
    src = workdir / f"build-{version}"
    src.mkdir(parents=True)
    (src / f"{CODE}.pyx").write_text(f'VERSION = "{version}"\n', encoding="utf-8")
    (src / "setup.py").write_text(
        "from setuptools import setup\nfrom Cython.Build import cythonize\n"
        f"setup(ext_modules=cythonize('{CODE}.pyx', quiet=True))\n",
        encoding="utf-8",
    )
    subprocess.run(  # nosec B603 - fixed argv
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=src, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    so = next(p for p in src.iterdir() if p.name.startswith(CODE) and p.suffix == ".so")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(so, arcname=so.name)
        meta = json.dumps({"code": CODE, "version": version}).encode()
        info = tarfile.TarInfo("metadata.json")
        info.size = len(meta)
        tar.addfile(info, io.BytesIO(meta))
    return buffer.getvalue()


class LicenseServer:  # pylint: disable=too-many-instance-attributes
    """The module endpoints of the license server, with a chaos switch."""

    def __init__(self, bundles: Dict[str, bytes]):
        self.bundles = bundles
        self.published = OLD
        self.chaos = False
        self.stale_until = 0.0  # downloads still serve OLD until then (CDN lag)
        self.counts: Dict[str, int] = {}

    def _count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    async def versions(self, _request):
        bundle = self.bundles[self.published]
        self._count("versions")
        return web.json_response({
            "modules": [{"code": CODE, "latest_version": self.published,
                         "file_hash": hashlib.sha512(bundle).hexdigest()}],
            "plugins": [],
        })  # fmt: skip

    async def download(self, _request):
        self._count("download")
        version = self.published
        if self.chaos:
            roll = random.random()  # nosec B311
            if roll < 0.4:
                self._count("download_503")
                return web.Response(status=503, text="overloaded")
            if roll < 0.55:
                self._count("download_stalled")
                await asyncio.sleep(random.uniform(2, 6))  # nosec B311
            if time.monotonic() < self.stale_until:
                version = OLD
                self._count("download_stale")
        bundle = self.bundles[version]
        digest = hashlib.sha512(bundle).hexdigest()
        if self.chaos and random.random() < 0.15:  # nosec B311
            self._count("download_corrupt")
            bundle = bundle[: len(bundle) // 2] + b"\0" * (
                len(bundle) - len(bundle) // 2
            )
        return web.Response(body=bundle, headers={
            "X-Content-SHA512": digest, "X-Module-Version": version,
            "Content-Type": "application/gzip",
        })  # fmt: skip

    async def start(self) -> int:
        app = web.Application()
        app.router.add_get("/api/v1/modules/versions/{p}/{a}/{py}", self.versions)
        app.router.add_get(
            "/api/v1/modules/download/{code}/{v}/{p}/{a}/{py}", self.download
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        return site._server.sockets[0].getsockname()[
            1
        ]  # pylint: disable=protected-access


class Customer:  # pylint: disable=too-many-instance-attributes
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, index: int, root: Path, port: int, cycle: float, legacy: bool = False
    ):
        self.index = index
        self.dir = root / f"customer-{index:03d}"
        self.dir.mkdir(parents=True)
        config = {
            "database": {"user": "sqlite", "password": "", "host": "", "port": 0,
                         "name": str(self.dir / "customer.db")},
            "license": {"key": "LOADTEST-KEY", "phone_home_url": f"http://127.0.0.1:{port}",
                        "modules_path": str(self.dir / "modules")},
            "security": {"jwt_secret": "x" * 48, "password_salt": "y" * 32,
                         "admin_userid": "admin@sysmanage.org", "admin_password": "Load-Admin-1"},
            "logging": {"level": "CRITICAL"},
            "multitenancy": {"enabled": False}, "vault": {"enabled": False},
            "email": {"enabled": False},
        }  # fmt: skip
        (self.dir / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        self.cycle = cycle
        self.legacy = legacy
        self.proc = None
        self.had_engine = False
        self.gaps = 0
        self.gap_samples = []
        self.version = None
        self.failed_updates = 0

    async def start(self):
        env = {**os.environ, "PYTHONPATH": str(REPO)}
        stderr = self._stderr()
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, str(REPO / "tests/load/publish_customer.py"),
            str(self.dir / "config.yaml"), CODE, str(self.cycle),
            *(["legacy"] if self.legacy else []),
            stdout=asyncio.subprocess.PIPE, stderr=stderr, env=env,
        )  # fmt: skip
        os.close(stderr)
        asyncio.ensure_future(self._read())

    def _stderr(self):
        # The child gets its own copy of this descriptor; start() closes ours.
        with open(self.dir / "stderr.log", "wb") as handle:
            return os.dup(handle.fileno())

    def stderr_tail(self, lines=15) -> str:
        try:
            text = (self.dir / "stderr.log").read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    async def _read(self):
        async for raw in self.proc.stdout:
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if line["kind"] == "sample":
                ok = line["loaded"] and line["on_disk"]
                if ok:
                    self.had_engine = True
                elif self.had_engine:
                    self.gaps += 1
                    self.gap_samples.append(line)
                self.version = line["version"]
            elif line.get("results", {}).get(CODE) is False:
                self.failed_updates += 1

    async def stop(self):
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()


async def _until(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.5)
    return False


async def run(args) -> dict:  # pylint: disable=too-many-locals
    root = Path(tempfile.mkdtemp(prefix="publish-scenario-"))
    try:
        print("building the test engine (two versions) ...")
        bundles = {v: build_engine(root, v) for v in (OLD, NEW)}
        server = LicenseServer(bundles)
        port = await server.start()
        customers = [Customer(i, root, port, args.cycle_seconds, args.legacy)
                     for i in range(args.customers)]  # fmt: skip
        for customer in customers:
            await customer.start()
        print(
            f"{OLD} published; waiting for {args.customers} customers to install it ..."
        )
        installed = await _until(lambda: all(c.version == OLD and c.had_engine for c in customers),
                                 args.install_timeout)  # fmt: skip
        failures_before = sum(c.failed_updates for c in customers)
        print(f"  all on {OLD}: {installed}; publishing {NEW} under chaos "
              f"for {args.chaos_seconds}s ...")  # fmt: skip
        server.published = NEW
        server.chaos = True
        server.stale_until = time.monotonic() + args.chaos_seconds / 3
        await asyncio.sleep(args.chaos_seconds)
        server.chaos = False
        failures_in_chaos = sum(c.failed_updates for c in customers) - failures_before
        print(f"  chaos over ({failures_in_chaos} failed updates); converging ...")
        converged = await _until(lambda: all(c.version == NEW for c in customers),
                                 args.converge_timeout)  # fmt: skip
        await asyncio.sleep(2)  # a few more samples on the new version
        for customer in customers:
            await customer.stop()
        trouble = next((c for c in customers if not c.had_engine or c.gaps), None)
        report = {
            "customers": args.customers,
            "installed_old": installed,
            "converged_new": converged,
            "failed_updates_during_chaos": failures_in_chaos,
            "server_counts": server.counts,
            "customers_with_gaps": sum(1 for c in customers if c.gaps),
            "gap_samples": [s for c in customers for s in c.gap_samples][:20],
            "versions_at_end": sorted({str(c.version) for c in customers}),
            "never_had_engine": sum(1 for c in customers if not c.had_engine),
            "first_troubled_customer_stderr": (
                trouble.stderr_tail() if trouble else None
            ),
        }
        violations = []
        if not installed:
            violations.append(
                f"not every customer installed {OLD} in {args.install_timeout}s"
            )
        if report["customers_with_gaps"]:
            violations.append(f"{report['customers_with_gaps']} customers were WITHOUT "
                              "their engine during the publish")  # fmt: skip
        if not converged:
            violations.append(
                f"not every customer reached {NEW}: {report['versions_at_end']}"
            )
        if not failures_in_chaos:
            violations.append(
                "no update failed during the chaos: the run proved nothing"
            )
        report["violations"] = violations
        return report
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--customers", type=int, default=40)
    parser.add_argument(
        "--cycle-seconds",
        type=float,
        default=3.0,
        help="each customer's update interval (production: 6 h)",
    )
    parser.add_argument("--chaos-seconds", type=float, default=60.0)
    parser.add_argument("--install-timeout", type=float, default=120.0)
    parser.add_argument("--converge-timeout", type=float, default=120.0)
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="negative control: customers delete their engine before "
        "downloading, as before 22.4 -- the run must FAIL",
    )
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    report = asyncio.run(run(args))
    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "gap_samples"}, indent=2))
    if report["violations"]:
        print("\nPhase 22.4 publish criterion NOT met:")
        for line in report["violations"]:
            print(f"  - {line}")
        return 2
    print("\nNo customer was without its engine during the publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
