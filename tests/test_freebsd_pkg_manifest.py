# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The FreeBSD server package lists every file and installable dependencies.

Until 2026-11-05 the package had no ``files`` section (so ``pkg`` installed
nothing), depended on ``py311-*`` packages FreeBSD no longer builds, and its
nginx config carried the port's literal ``%%PREFIX%%`` tokens (found by
installing it on a fresh FreeBSD 14.5 VM).
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "freebsd" / "build_pkg_manifest.py"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file modes; the package is built on Linux"
)


def _load():
    spec = importlib.util.spec_from_file_location("build_pkg_manifest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage(root: Path) -> Path:
    lib = root / "usr/local/lib/sysmanage/backend"
    lib.mkdir(parents=True)
    (lib / "main.py").write_text("print('server')\n")
    rc = root / "usr/local/etc/rc.d/sysmanage"
    rc.parent.mkdir(parents=True)
    rc.write_text("#!/bin/sh\n")
    rc.chmod(0o775)
    hcl = root / "usr/local/etc/openbao/openbao.hcl"
    hcl.parent.mkdir(parents=True)
    hcl.write_text("storage {}\n")
    return root


def _build(tmp_path, monkeypatch) -> dict:
    staging = _stage(tmp_path / "staging")
    monkeypatch.setattr(sys, "argv", ["x", str(staging), "3.12.1.99"])
    assert _load().main() == 0
    return json.loads((staging / "+MANIFEST").read_text())


def test_every_file_is_listed_with_its_checksum_and_mode(tmp_path, monkeypatch):
    files = _build(tmp_path, monkeypatch)["files"]
    main = "/usr/local/lib/sysmanage/backend/main.py"
    assert set(files) == {
        main,
        "/usr/local/etc/rc.d/sysmanage",
        "/usr/local/etc/openbao/openbao.hcl",
    }
    staged = tmp_path / "staging" / main.lstrip("/")
    assert files[main]["sum"] == f"1${hashlib.sha256(staged.read_bytes()).hexdigest()}"
    assert files[main]["perm"] == "0644"
    assert files["/usr/local/etc/rc.d/sysmanage"]["perm"] == "0755"
    assert files["/usr/local/etc/openbao/openbao.hcl"]["perm"] == "0640"
    # The archive carries the staged modes, so they must match the manifest.
    rc = tmp_path / "staging/usr/local/etc/rc.d/sysmanage"
    assert oct(rc.stat().st_mode & 0o777) == "0o755"


def test_dependencies_come_from_the_port_in_the_current_python_flavor(
    tmp_path, monkeypatch
):
    deps = _build(tmp_path, monkeypatch)["deps"]
    assert not [name for name in deps if name.startswith("py311")]
    # Imported by the backend; the port's list once lacked both.
    assert deps["py312-regex"]["origin"] == "textproc/py-regex"
    assert "py312-packaging" in deps
    assert deps["python312"]["origin"] == "lang/python312"
    assert deps["nginx"]["origin"] == "www/nginx"
    # Origins are plain category/port, without the port's @flavor suffix.
    assert not [d for d in deps.values() if "@" in d["origin"]]


def test_post_install_compiles_nothing_and_starts_no_daemon(tmp_path, monkeypatch):
    script = _build(tmp_path, monkeypatch)["scripts"]["post-install"]
    assert "pip install" not in script and "python3.11" not in script
    assert "--system-site-packages" in script
    # pkg reaps processes a package script leaves running.
    assert "service openbao start >" not in script


def test_an_empty_staging_tree_is_refused(tmp_path, monkeypatch):
    (tmp_path / "staging" / "usr").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path / "staging"), "1.0"])
    assert _load().main() == 1
