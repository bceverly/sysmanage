# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The gate on async route handlers that never await (production 2026-11-18)."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_async_handlers",
    Path(__file__).resolve().parent.parent / "scripts" / "check_async_handlers.py",
)
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

SOURCE = """
from fastapi import APIRouter
router = APIRouter()

@router.get("/blocking")
async def blocking(db=None):
    return db.query("x")

@router.post("/awaits")
async def awaits(ws=None):
    await ws.send("x")

@router.get("/plain")
def plain(db=None):
    return db.query("x")

@router.get("/nested-await-only")
async def nested_await_only():
    async def helper():
        await something()
    return helper

async def not_a_route():
    return 1

@router.api_route("/any", methods=["GET"])
async def any_method():
    async with lock:
        return 1
"""


@pytest.fixture
def tree(tmp_path, monkeypatch):
    api = tmp_path / "backend" / "api"
    api.mkdir(parents=True)
    (api / "things.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "backend" / "tests").mkdir()
    (tmp_path / "backend" / "tests" / "test_x.py").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setattr(gate, "REPO", tmp_path)
    monkeypatch.setattr(gate, "ROOT", tmp_path / "backend")
    monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "allow.txt")
    return tmp_path


def test_only_async_routes_that_never_await_are_flagged(tree):
    found = sorted(gate.offenders(tree / "backend"))
    # An await inside a nested function does not make the handler await;
    # plain def, awaiting, `async with`, non-routes and tests are left alone.
    assert found == [
        "backend/api/things.py:blocking",
        "backend/api/things.py:nested_await_only",
    ]


def test_a_new_offender_fails_with_the_fix(tree, capsys):
    gate.write_allowlist(["backend/api/things.py:blocking"], tree / "allow.txt")
    assert gate.main([]) == 1
    out = capsys.readouterr().out
    assert "nested_await_only" in out and "Change `async def` to `def`" in out
    assert "Do NOT add it to the allowlist" in out


def test_a_fixed_entry_must_leave_the_list(tree, capsys):
    gate.write_allowlist(
        ["backend/api/things.py:blocking", "backend/api/things.py:nested_await_only",
         "backend/api/things.py:converted_since"],
        tree / "allow.txt",
    )  # fmt: skip
    assert gate.main([]) == 1
    assert "converted_since" in capsys.readouterr().out
    assert gate.main(["--prune"]) == 0
    assert "converted_since" not in (tree / "allow.txt").read_text(encoding="utf-8")
    assert gate.main([]) == 0


def test_prune_never_adds(tree):
    gate.write_allowlist([], tree / "allow.txt")
    gate.main(["--prune"])
    assert gate.read_allowlist(tree / "allow.txt") == []


def test_a_loop_safe_marker_with_a_reason_keeps_a_handler_async(tmp_path, monkeypatch):
    api = tmp_path / "backend" / "api"
    api.mkdir(parents=True)
    (api / "health.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
        '@router.get("/health")\n'
        "async def health():  # loop-safe: touches nothing\n"
        '    return {"ok": True}\n\n'
        '@router.get("/no-reason")\n'
        "async def no_reason():  # loop-safe:\n"
        '    return {"ok": True}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "REPO", tmp_path)
    # A marker without a reason does not count.
    assert list(gate.offenders(tmp_path / "backend")) == [
        "backend/api/health.py:no_reason"
    ]
