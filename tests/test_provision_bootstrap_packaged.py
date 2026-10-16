# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""scripts/provision_bootstrap.py on a packaged single-node server: as root
it needs no arguments -- the OpenBAO token comes from the appliance's init
material and the Postgres role goes through the local superuser over stdin,
so no password-bearing SQL file is left for the operator to apply."""

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provision_bootstrap.py"


@pytest.fixture(scope="module")
def boot():
    spec = importlib.util.spec_from_file_location("provision_bootstrap", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path, **overrides):
    values = {
        "bao_token": "",
        "bao_init_file": str(tmp_path / "init.json"),
        "pg_host": "localhost",
        "pg_port": 5432,
        "pg_db": "postgres",
        "pg_superuser": "postgres",
        "provisioner_user": "sysmanage_provisioner",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class TestToken:
    def test_explicit_token_wins(self, boot, tmp_path, monkeypatch):
        monkeypatch.setenv("BAO_TOKEN", "env")
        assert boot._bao_token(_args(tmp_path, bao_token="flag")) == "flag"

    def test_environment_next(self, boot, tmp_path, monkeypatch):
        monkeypatch.setenv("BAO_TOKEN", "env")
        assert boot._bao_token(_args(tmp_path)) == "env"

    def test_appliance_init_material_last(self, boot, tmp_path, monkeypatch):
        monkeypatch.delenv("BAO_TOKEN", raising=False)
        (tmp_path / "init.json").write_text(json.dumps({"root_token": "root"}))
        assert boot._bao_token(_args(tmp_path)) == "root"

    def test_nothing_says_how_to_supply_one(self, boot, tmp_path, monkeypatch):
        monkeypatch.delenv("BAO_TOKEN", raising=False)
        with pytest.raises(SystemExit) as exc:
            boot._bao_token(_args(tmp_path))
        assert "--bao-token" in str(exc.value)
        assert "init.json" in str(exc.value)


class TestLocalApply:
    # raising=False: Windows has no os.geteuid; the code path under test is
    # the POSIX one, and it checks for geteuid itself.

    def _as_root(self, boot, monkeypatch, have=("psql", "runuser")):
        monkeypatch.setattr(boot.os, "geteuid", lambda: 0, raising=False)
        monkeypatch.setattr(
            boot.shutil,
            "which",
            lambda name: f"/usr/bin/{name}" if name in have else None,
        )

    def test_root_on_local_postgres_pipes_sql_to_psql(
        self, boot, tmp_path, monkeypatch
    ):
        self._as_root(boot, monkeypatch)
        seen = {}

        def fake_run(argv, **kwargs):
            seen["argv"], seen["input"] = argv, kwargs["input"]
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(boot.subprocess, "run", fake_run)
        assert boot._apply_pg_provisioner_sql(_args(tmp_path), "pw123")
        assert seen["argv"][:4] == ["runuser", "-u", "postgres", "--"]
        assert "ON_ERROR_STOP=1" in seen["argv"]
        assert "PASSWORD 'pw123'" in seen["input"]
        assert "pw123" not in " ".join(seen["argv"])

    def test_psql_failure_falls_back(self, boot, tmp_path, monkeypatch, capsys):
        self._as_root(boot, monkeypatch)
        monkeypatch.setattr(
            boot.subprocess,
            "run",
            lambda argv, **_: subprocess.CompletedProcess(argv, 1, "", "role error"),
        )
        assert not boot._apply_pg_provisioner_sql(_args(tmp_path), "pw")
        assert "role error" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "euid,host,have",
        [
            (1000, "localhost", ("psql", "runuser")),
            (0, "db.example.com", ("psql", "runuser")),
            (0, "localhost", ("runuser",)),
            (0, "localhost", ("psql",)),
        ],
    )
    def test_not_possible_here_is_declined(
        self, boot, tmp_path, monkeypatch, euid, host, have
    ):
        monkeypatch.setattr(boot.os, "geteuid", lambda: euid, raising=False)
        monkeypatch.setattr(
            boot.shutil,
            "which",
            lambda name: f"/usr/bin/{name}" if name in have else None,
        )
        monkeypatch.setattr(
            boot.subprocess, "run", lambda *a, **k: pytest.fail("must not run psql")
        )
        assert not boot._apply_pg_provisioner_sql(_args(tmp_path, pg_host=host), "pw")

    def test_bad_identifier_is_refused(self, boot, tmp_path):
        with pytest.raises(SystemExit):
            boot._provisioner_sql(_args(tmp_path, provisioner_user='x"; DROP'), "pw")
