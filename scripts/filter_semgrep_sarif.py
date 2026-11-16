#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Filter ``semgrep ci`` SARIF before it is uploaded to GitHub Code Scanning.

Two kinds of finding are dropped:

1. Findings Semgrep marked suppressed (``nosemgrep``).  Code Scanning ignores
   SARIF's ``suppressions`` property, so they would otherwise show as open
   (https://github.com/semgrep/semgrep/issues/6658).
2. Lockfile findings accepted in ``.semgrep-accepted.json``.  Lockfiles are
   JSON and cannot carry ``nosemgrep``; listing a whole lockfile in
   ``.semgrepignore`` would hide every future advisory on it.  An entry
   matches only on rule + file + package + the package's LOCKED version, so
   an upgrade that is still affected, or the same advisory on another
   package, is reported again.

Usage: filter_semgrep_sarif.py RAW.sarif OUT.sarif [ACCEPTED.json]
"""

import json
import re
import sys
from pathlib import Path

_PACKAGE_KEY = re.compile(r'"((?:[^"]*/)?node_modules/[^"]+)"')


def _location(result):
    """``(uri, snippet)`` of a result's first location."""
    try:
        physical = result["locations"][0]["physicalLocation"]
    except (KeyError, IndexError, TypeError):
        return None, ""
    uri = physical.get("artifactLocation", {}).get("uri")
    snippet = physical.get("region", {}).get("snippet", {}).get("text", "")
    return uri, snippet


def _locked_version(root, uri, key, cache):
    """The version ``key`` (``node_modules/<pkg>``) is locked at in ``uri``."""
    if uri not in cache:
        try:
            lock = json.loads((root / uri).read_text(encoding="utf-8"))
            cache[uri] = lock.get("packages", {})
        except (OSError, ValueError):
            cache[uri] = {}
    return (cache[uri].get(key) or {}).get("version")


def _accepting_entry(result, accepted, root, cache):
    """The accepted entry covering ``result``, or None."""
    uri, snippet = _location(result)
    found = _PACKAGE_KEY.search(snippet)
    if not uri or not found:
        return None
    key = found.group(1)
    for entry in accepted:
        if (
            result.get("ruleId") == entry["rule"]
            and uri in entry["paths"]
            and key.rsplit("node_modules/", 1)[-1] == entry["package"]
            and _locked_version(root, uri, key, cache) == entry["version"]
        ):
            return entry
    return None


def filter_sarif(sarif, accepted, root):
    """Drop suppressed and accepted results in place.

    Returns ``(dropped, unused)``: how many results were dropped, and the
    accepted entries that matched nothing (stale, to be deleted)."""
    used, dropped, cache = set(), 0, {}
    for run in sarif.get("runs", []):
        kept = []
        for result in run.get("results", []):
            if result.get("suppressions"):
                dropped += 1
                continue
            entry = _accepting_entry(result, accepted, root, cache)
            if entry is not None:
                used.add(id(entry))
                dropped += 1
                continue
            kept.append(result)
        run["results"] = kept
    return dropped, [entry for entry in accepted if id(entry) not in used]


def main(argv):
    """Read RAW, write the filtered OUT; report stale accepted entries."""
    if len(argv) not in (3, 4):
        print(__doc__.strip().splitlines()[-1])
        return 2
    raw, out = Path(argv[1]), Path(argv[2])
    accepted_path = Path(argv[3] if len(argv) == 4 else ".semgrep-accepted.json")
    accepted = []
    if accepted_path.exists():
        accepted = json.loads(accepted_path.read_text(encoding="utf-8"))["accepted"]
    sarif = json.loads(raw.read_text(encoding="utf-8"))
    dropped, unused = filter_sarif(sarif, accepted, accepted_path.resolve().parent)
    out.write_text(json.dumps(sarif), encoding="utf-8")
    print(f"Dropped {dropped} suppressed or accepted Semgrep finding(s).")
    for entry in unused:
        print(
            f"::warning::{accepted_path} entry for {entry['package']} "
            f"{entry['version']} ({entry['rule']}) matched no finding. If the "
            "package was upgraded and the finding is gone, delete the entry. "
            "If the finding is back on a new version, decide again: fix it or "
            "update the entry's version."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
