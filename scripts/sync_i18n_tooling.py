#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
"""
Propagate the shared i18n tooling to the sibling repos.

WHY
---
``i18n_strict.py`` is the gate that fails a build on English-identical, stale
or wrong-language translations, and all four repos need it.  Cython's textual
include (the ``agent_install.pxi`` case) at least keeps its copies in one
repository; these live in four SEPARATE git repos, so there is no import, no
submodule, and nothing that notices when they diverge.

They diverged.  Measured 2026-08-12: four copies of ``i18n_strict.py`` with
four different hashes and five of ``i18n_validate.py`` with five, while only
36 lines out of ~590 actually differ — and most of THAT is black re-wrapping
noise.  The real per-repo difference is the ``SURFACES`` table and nothing
else.  The cost is not theoretical: adding one line to the failure hint that
day meant hand-editing three repos, which is exactly how the drift starts.

WHAT IS ALLOWED TO DIFFER
-------------------------
Two things, both preserved verbatim from the target:

  * the **licence header** -- sysmanage-professional-plus is PROPRIETARY and
    must never carry the AGPL header the other three use; and
  * the **per-repo surfaces block**, delimited by the ``BEGIN``/``END``
    sentinels below.  Pro+ builds its list with a comprehension over
    ``module-source`` engines, docs uses one flat ``json-flat`` surface -- so
    this is a whole statement, not a value.

Everything else is rewritten from the canonical copy.

Usage:
  python3 scripts/sync_i18n_tooling.py            # rewrite the copies
  python3 scripts/sync_i18n_tooling.py --check    # exit 1 if any has drifted
  python3 scripts/sync_i18n_tooling.py --diff     # show what would change
"""

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent

BEGIN = "# ===== per-repo surfaces: the ONLY part of this file that differs =====\n"
END = "# ===== end per-repo surfaces ==========================================\n"

# (canonical path relative to this repo, path relative to each sibling repo).
# ``i18n_strict.py`` carries a per-repo config block; ``i18n_hashes.py`` does
# not, and the code below handles both.
SHARED = [
    ("scripts/i18n_strict.py", "scripts/i18n_strict.py"),
]

# sysmanage keeps the translation backfill under scripts/translation-service/,
# the other repos beside their translate script.  Same file, different home.
HASHES_HOME = {
    "sysmanage": "scripts/translation-service/i18n_hashes.py",
    "sysmanage-agent": None,  # .po only: no JSON sidecar, nothing to record
    "sysmanage-professional-plus": "scripts/i18n_hashes.py",
    "sysmanage-docs": "scripts/i18n_hashes.py",
}

TARGETS = ["sysmanage-agent", "sysmanage-professional-plus", "sysmanage-docs"]


def split_header(text):
    """(licence header, everything from the module docstring onward).

    The header is the shebang plus the contiguous comment block above the
    docstring -- which is precisely the part that must NOT be copied between an
    AGPL repo and the proprietary one.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.lstrip().startswith('"""'):
            return "".join(lines[:i]), "".join(lines[i:])
    raise SystemExit("no module docstring found; refusing to guess the header")


def split_config(text):
    """(before, config block, after) around the surfaces sentinels."""
    if BEGIN not in text or END not in text:
        return text, None, ""
    before, rest = text.split(BEGIN, 1)
    block, after = rest.split(END, 1)
    return before, block, after


def render(canonical_text, target_text):
    """Canonical body, wearing the target's header and surfaces block."""
    _, canon_body = split_header(canonical_text)
    target_header, target_body = split_header(target_text)

    canon_before, canon_block, canon_after = split_config(canon_body)
    _, target_block, _ = split_config(target_body)
    if canon_block is None or target_block is None:
        # No config block in this file (e.g. i18n_hashes.py): body copies whole.
        return target_header + canon_body
    return target_header + canon_before + BEGIN + target_block + END + canon_after


def pairs():
    """(label, canonical path, target path) for every file to keep in sync."""
    out = []
    for canon_rel, target_rel in SHARED:
        for repo in TARGETS:
            out.append((repo, ROOT / canon_rel, SIBLINGS / repo / target_rel))
    canon_hashes = ROOT / HASHES_HOME["sysmanage"]
    for repo in TARGETS:
        rel = HASHES_HOME.get(repo)
        if rel:
            out.append((repo, canon_hashes, SIBLINGS / repo / rel))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 on drift")
    parser.add_argument("--diff", action="store_true", help="show the drift")
    args = parser.parse_args()

    drifted, missing, wrote, skipped = [], [], [], set()
    for repo, canon, target in pairs():
        if not canon.exists():
            missing.append(f"{canon} (canonical)")
            continue
        # A sibling repo that is not checked out is not drift.  CI clones ONE
        # repo, so failing here would break every pipeline; this check is only
        # meaningful on a machine holding all four.
        if not (SIBLINGS / repo).is_dir():
            skipped.add(repo)
            continue
        if not target.exists():
            missing.append(str(target))
            continue
        want = render(canon.read_text(encoding="utf-8"), target.read_text(encoding="utf-8"))
        have = target.read_text(encoding="utf-8")
        if want == have:
            continue
        drifted.append(f"{repo}/{target.name}")
        if args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    have.splitlines(keepends=True),
                    want.splitlines(keepends=True),
                    fromfile=f"{target} (current)",
                    tofile=f"{target} (synced)",
                )
            )
        if not (args.check or args.diff):
            target.write_text(want, encoding="utf-8")
            wrote.append(f"{repo}/{target.name}")

    for path in missing:
        print(f"  MISSING  {path}", file=sys.stderr)
    for name in wrote:
        print(f"  synced   {name}")
    for repo in sorted(skipped):
        print(f"  skipped  {repo} (not checked out beside this repo)")

    if args.check or args.diff:
        if drifted:
            print(
                "\nDRIFT: "
                + ", ".join(drifted)
                + "\n  Edit the canonical copy in sysmanage/, then run:"
                + "\n    python3 scripts/sync_i18n_tooling.py",
                file=sys.stderr,
            )
            return 1
        print("OK: shared i18n tooling is in sync across all repos")
    elif not wrote:
        print("OK: already in sync")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
