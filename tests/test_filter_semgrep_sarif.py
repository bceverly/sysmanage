# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""The Semgrep SARIF filter hides exactly what is accepted, and nothing more:
a lockfile finding is dropped only on rule + file + package + locked version."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "filter_semgrep_sarif", ROOT / "scripts" / "filter_semgrep_sarif.py"
)
sarif_filter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sarif_filter)

RULE = "ssc-9c34c675-756b-44e8-9512-28718930fef2"
LOCK = "frontend/package-lock.json"


def _result(rule=RULE, uri=LOCK, package="playwright-core", suppressed=False):
    result = {
        "ruleId": rule,
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {
                        "snippet": {"text": f'    "node_modules/{package}": {{'}
                    },
                }
            }
        ],
    }
    if suppressed:
        result["suppressions"] = [{"kind": "inSource"}]
    return result


def _entry(version="1.65.1", package="playwright-core"):
    return {"rule": RULE, "package": package, "version": version, "paths": [LOCK]}


@pytest.fixture(name="root")
def _root(tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / LOCK).write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/playwright-core": {"version": "1.65.1"},
                    "node_modules/puppeteer": {"version": "24.0.0"},
                }
            }
        )
    )
    return tmp_path


def _run(results, accepted, root):
    sarif = {"runs": [{"results": results}]}
    dropped, unused = sarif_filter.filter_sarif(sarif, accepted, root)
    return sarif["runs"][0]["results"], dropped, unused


def test_an_accepted_finding_at_its_locked_version_is_dropped(root):
    kept, dropped, unused = _run([_result()], [_entry()], root)
    assert kept == [] and dropped == 1 and unused == []


def test_nosemgrep_suppressed_findings_are_dropped(root):
    kept, dropped, _ = _run([_result(rule="other", suppressed=True)], [], root)
    assert kept == [] and dropped == 1


@pytest.mark.parametrize(
    "result",
    [
        _result(rule="ssc-some-new-advisory"),  # a new advisory on the file
        _result(package="puppeteer"),  # the same advisory, another package
        _result(uri="other/package-lock.json"),  # a file not listed
    ],
)
def test_anything_else_on_the_lockfile_is_still_reported(root, result):
    kept, dropped, unused = _run([result], [_entry()], root)
    assert kept == [result] and dropped == 0 and len(unused) == 1


def test_an_upgrade_that_is_still_affected_is_reported_again(root):
    kept, _, unused = _run([_result()], [_entry(version="1.64.0")], root)
    assert len(kept) == 1 and unused == [_entry(version="1.64.0")]


def test_main_warns_about_a_stale_entry(root, capsys):
    raw, out = root / "raw.sarif", root / "out.sarif"
    raw.write_text(json.dumps({"runs": [{"results": []}]}))
    accepted = root / ".semgrep-accepted.json"
    accepted.write_text(json.dumps({"accepted": [_entry()]}))
    assert sarif_filter.main(["x", str(raw), str(out), str(accepted)]) == 0
    assert json.loads(out.read_text()) == {"runs": [{"results": []}]}
    assert "::warning::" in capsys.readouterr().out


def test_the_real_accepted_entries_match_the_real_lockfiles():
    """Each accepted entry still names the version actually locked, in every
    file it lists -- the two lockfile copies cannot drift apart under it."""
    accepted = json.loads((ROOT / ".semgrep-accepted.json").read_text())["accepted"]
    for entry in accepted:
        for path in entry["paths"]:
            lock = json.loads((ROOT / path).read_text())["packages"]
            key = f"node_modules/{entry['package']}"
            locked = (lock.get(key) or {}).get("version")
            assert locked == entry["version"], (
                f"{path} now locks {entry['package']} {locked}, but "
                f".semgrep-accepted.json accepts {entry['version']}. "
                "1. Run the Semgrep scan (make security-semgrep with "
                "SEMGREP_APP_TOKEN set). "
                f"2. If {entry['rule']} no longer fires, delete the entry. "
                "3. If it still fires, decide again: fix it, or update the "
                "entry's version and reason."
            )
