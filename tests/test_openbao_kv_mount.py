# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""scripts/openbao_init_unseal.py: a fresh non-dev OpenBAO has no ``secret/``
mount, so the init unit enables kv-v2 there (once) -- otherwise every secret
write and tenant provisioning fails with "no handler for route"."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openbao_init_unseal.py"


@pytest.fixture(scope="module")
def unseal():
    spec = importlib.util.spec_from_file_location("openbao_init_unseal", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeBao:
    """Records calls; answers sys/mounts from ``mounts``."""

    def __init__(self, mounts, list_status=200, enable_status=204):
        self.mounts = mounts
        self.list_status = list_status
        self.enable_status = enable_status
        self.calls = []

    def __call__(self, addr, path, method="GET", payload=None, token=None, **_):
        self.calls.append((method, path, payload, token))
        if method == "GET" and path == "/v1/sys/mounts":
            return self.list_status, {"data": self.mounts}
        return self.enable_status, None


def test_fresh_server_gets_kv_v2_at_secret(unseal, monkeypatch):
    bao = _FakeBao({"sys/": {"type": "system"}})
    monkeypatch.setattr(unseal, "_api", bao)
    assert unseal._ensure_kv_mount("http://bao", "tok", "secret")
    assert bao.calls[-1] == (
        "POST",
        "/v1/sys/mounts/secret",
        {"type": "kv", "options": {"version": "2"}},
        "tok",
    )


def test_existing_kv_v2_mount_is_left_alone(unseal, monkeypatch):
    bao = _FakeBao({"secret/": {"type": "kv", "options": {"version": "2"}}})
    monkeypatch.setattr(unseal, "_api", bao)
    assert unseal._ensure_kv_mount("http://bao", "tok", "secret")
    assert [c[0] for c in bao.calls] == ["GET"]


def test_a_different_engine_at_the_path_is_not_replaced(unseal, monkeypatch, capsys):
    bao = _FakeBao({"secret/": {"type": "kv", "options": {"version": "1"}}})
    monkeypatch.setattr(unseal, "_api", bao)
    assert unseal._ensure_kv_mount("http://bao", "tok", "secret")
    assert [c[0] for c in bao.calls] == ["GET"]
    assert "not kv-v2" in capsys.readouterr().err


@pytest.mark.parametrize("list_status,enable_status", [(403, 204), (200, 400)])
def test_failures_are_reported(unseal, monkeypatch, capsys, list_status, enable_status):
    bao = _FakeBao({}, list_status=list_status, enable_status=enable_status)
    monkeypatch.setattr(unseal, "_api", bao)
    assert not unseal._ensure_kv_mount("http://bao", "tok", "secret")
    assert "ERROR" in capsys.readouterr().err


def test_main_ensures_the_mount_after_unseal(unseal, monkeypatch, tmp_path):
    keyfile = tmp_path / "init.json"
    keyfile.write_text('{"root_token": "tok", "unseal_keys": []}')
    seen = []
    monkeypatch.setattr(unseal, "_wait_for_listener", lambda addr: True)
    monkeypatch.setattr(unseal, "_ensure_unsealed", lambda addr, kf: 0)
    monkeypatch.setattr(
        unseal, "_ensure_kv_mount", lambda addr, tok, mount: seen.append(mount)
    )
    monkeypatch.setattr(
        "sys.argv", ["x", "--keyfile", str(keyfile), "--kv-mount", "kv"]
    )
    assert unseal.main() == 0
    assert seen == ["kv"]
