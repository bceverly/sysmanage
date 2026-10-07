# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""backend._expose_bundled_libpq: Windows finds libpq only along PATH."""

import os
import sys

import backend


def _fake_install(tmp_path, monkeypatch, with_dll):
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    if with_dll:
        (scripts / "libpq.dll").write_bytes(b"")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))
    monkeypatch.setenv("PATH", "C:\\Windows")
    return scripts


def test_prepends_the_folder_holding_libpq(tmp_path, monkeypatch):
    scripts = _fake_install(tmp_path, monkeypatch, with_dll=True)
    backend._expose_bundled_libpq()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(scripts)


def test_leaves_path_alone_without_libpq(tmp_path, monkeypatch):
    _fake_install(tmp_path, monkeypatch, with_dll=False)
    backend._expose_bundled_libpq()
    assert os.environ["PATH"] == "C:\\Windows"


def test_does_not_add_it_twice(tmp_path, monkeypatch):
    scripts = _fake_install(tmp_path, monkeypatch, with_dll=True)
    backend._expose_bundled_libpq()
    backend._expose_bundled_libpq()
    assert os.environ["PATH"].split(os.pathsep).count(str(scripts)) == 1


def test_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("PATH", "/usr/bin")
    backend._expose_bundled_libpq()
    assert os.environ["PATH"] == "/usr/bin"
