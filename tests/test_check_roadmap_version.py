# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Tests for the ROADMAP Current Version gate (scripts/check_roadmap_version.py).

The line names the Target Release of the first phase whose exit gate is open;
it was hand-maintained and sat at v3.10.0.0 while Phase 25 was being built.
"""

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "check_roadmap_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_roadmap_version", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _roadmap(current, gate_24="x", gate_25=" "):
    return f"""# Roadmap

### Release Versioning

**Current Version:** {current}

## Phase 11: Air-Gap

**Target Release:** v2.3.0.0

## Phase 24: Backups

**Target Release:** **v3.12.0.0**

- [{gate_24}] **Phase exit gate** (see above): all tests pass

## Phase 25: Backup Completion

**Target Release:** **v3.13.0.0**

- [{gate_25}] **Phase exit gate** (see above): all tests pass

## Phase 26: Updates

**Target Release:** **v3.14.0.0**

- [ ] **Phase exit gate** (see above): all tests pass
"""


def test_the_current_phase_is_the_first_with_an_open_exit_gate():
    mod = _load()
    assert mod.current_phase(_roadmap("v3.13.0.0")) == ("Phase 25", "v3.13.0.0")
    # Phases with no explicit gate (0-11) are skipped, not taken as current.
    assert mod.current_phase(_roadmap("x", gate_24=" ")) == ("Phase 24", "v3.12.0.0")


def test_a_stale_line_fails_and_fix_rewrites_it(tmp_path, capsys):
    mod = _load()
    path = tmp_path / "ROADMAP.md"
    path.write_text(_roadmap("v3.10.0.0"), encoding="utf-8")
    assert mod.main(["--roadmap", str(path)]) == 1
    assert "Phase 25" in capsys.readouterr().out
    assert mod.main(["--roadmap", str(path), "--fix"]) == 0
    assert "**Current Version:** v3.13.0.0\n" in path.read_text(encoding="utf-8")
    assert mod.main(["--roadmap", str(path)]) == 0


def test_closing_a_phase_moves_the_line_to_the_next_release(tmp_path):
    mod = _load()
    path = tmp_path / "ROADMAP.md"
    path.write_text(_roadmap("v3.13.0.0", gate_25="x"), encoding="utf-8")
    assert mod.main(["--roadmap", str(path)]) == 1
    assert mod.main(["--roadmap", str(path), "--fix"]) == 0
    assert "**Current Version:** v3.14.0.0" in path.read_text(encoding="utf-8")


def test_the_real_roadmap_is_current():
    assert _load().main([]) == 0
