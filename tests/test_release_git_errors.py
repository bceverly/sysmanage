# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""``make release`` says what git said when a git step fails.

git's output is captured, so a refused commit used to surface only as a
Python traceback, with git's reason thrown away (v3.12.0.8, 2026-10-27).
Now a failed commit prints git's output, restores the version markers and
stops; a failed tag says the commit exists.  Git is never called: the script
module's ``subprocess.run`` is a fake.
"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
REFUSAL = "[pre-commit] black would reformat backend/x.py"


@pytest.fixture
def release(monkeypatch):
    spec = importlib.util.spec_from_file_location("release_git_errors", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Git:
    """A fake ``subprocess.run`` for git: each subcommand's (rc, out, err)."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, argv, **_kwargs):
        self.calls.append(argv[1:])
        rc, out, err = self.answers.get(argv[1], (0, "", ""))
        return types.SimpleNamespace(args=argv, returncode=rc, stdout=out, stderr=err)


def test_a_failing_checked_git_call_prints_what_git_said(release, monkeypatch, capsys):
    monkeypatch.setattr(
        release.subprocess, "run", _Git({"status": (128, "", "fatal: no")})
    )
    with pytest.raises(subprocess.CalledProcessError):
        release.git("status")
    err = capsys.readouterr().err
    assert "git status failed (exit 128); git said:" in err and "fatal: no" in err


def _main(release, monkeypatch, fake):
    monkeypatch.setattr(release.subprocess, "run", fake)
    monkeypatch.setattr(release, "known_tags", lambda: {(3, 12, 0, 7)})
    monkeypatch.setattr(release, "check_guards", lambda *a: None)
    monkeypatch.setattr(release, "bump_markers", lambda *a, **k: 0)
    dirty = iter([set(), {"installer/alpine/APKBUILD"}])
    monkeypatch.setattr(release, "dirty_paths", lambda: next(dirty))
    monkeypatch.setattr(release, "run_lint", lambda version: 0)
    restored = []
    monkeypatch.setattr(release, "restore_markers", restored.extend)
    monkeypatch.setattr(sys, "argv", ["release.py"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    return release.main(), restored


def test_a_refused_commit_prints_why_restores_the_markers_and_stops(
    release, monkeypatch, capsys
):
    fake = _Git({"diff": (1, "", ""), "commit": (1, "", REFUSAL)})
    code, restored = _main(release, monkeypatch, fake)
    err = capsys.readouterr().err
    assert code == 1
    assert REFUSAL in err and "NOTHING was committed or tagged" in err
    assert restored == ["installer/alpine/APKBUILD"]
    assert not any(call[0] in ("tag", "push") for call in fake.calls)


def test_a_refused_tag_says_the_commit_exists(release, monkeypatch, capsys):
    fake = _Git({"diff": (1, "", ""), "rev-parse": (0, "abc1234\n", ""),
                 "tag": (128, "", "fatal: tag 'v3.12.0.8' already exists")})  # fmt: skip
    code, restored = _main(release, monkeypatch, fake)
    err = capsys.readouterr().err
    assert code == 1 and restored == []
    assert "already exists" in err and "abc1234 exists LOCALLY" in err
    assert not any(call[0] == "push" for call in fake.calls)
