#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Gate: ROADMAP.md's ``Current Version:`` line names the phase in progress.

The line was hand-maintained and nothing checked it, so it drifted: it sat at
v3.3.0.0 through Phases 17-19, and at v3.10.0.0 (Phase 22) while Phase 25 was
being built (found 2026-11-09).  It is now derived from the ROADMAP itself,
not from git: the current phase is the first one whose final "Phase exit gate"
item is still unticked, and the current version is that phase's
``**Target Release:**``.  Closing a phase (ticking its exit gate) moves the
line to the next phase's release, and this gate fails until it does.

    python3 scripts/check_roadmap_version.py         # gate
    python3 scripts/check_roadmap_version.py --fix   # rewrite the line
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

ROADMAP = Path(__file__).resolve().parent.parent / "ROADMAP.md"
_PHASE = re.compile(r"(?m)^## (Phase \d+(?:\.\d+)?)\b[^\n]*\n")
_TARGET = re.compile(r"\*\*Target Release:\*\*\s*\**\s*(v\d+\.\d+\.\d+\.\d+)")
_GATE = re.compile(r"(?m)^- \[([ xX])\] \*\*Phase exit gate\*\*")
_CURRENT = re.compile(r"(?m)^(\*\*Current Version:\*\* )(v[\d.]+)\s*$")


def current_phase(text: str) -> Optional[Tuple[str, str]]:
    """``(phase, target release)`` of the first phase whose exit gate is
    open, or None when every phase with a gate is closed."""
    heads = list(_PHASE.finditer(text))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        body = text[head.end() : end]
        gate = _GATE.search(body)
        if gate is None or gate.group(1) != " ":
            continue  # no explicit gate (Phases 0-11), or closed
        target = _TARGET.search(body)
        if target is None:
            raise ValueError(
                f"{head.group(1)} has an open exit gate but no Target Release"
            )
        return head.group(1), target.group(1)
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--fix", action="store_true", help="rewrite the line")
    parser.add_argument("--roadmap", default=str(ROADMAP))
    args = parser.parse_args(argv)
    path = Path(args.roadmap)
    text = path.read_text(encoding="utf-8")
    found = current_phase(text)
    line = _CURRENT.search(text)
    if found is None or line is None:
        print("FAIL: ROADMAP.md has no open phase, or no 'Current Version:' line")
        return 1
    phase, version = found
    if line.group(2) == version:
        print(f"OK: Current Version {version} is {phase}'s Target Release")
        return 0
    if args.fix:
        path.write_text(
            text[: line.start(2)] + version + text[line.end(2) :], encoding="utf-8"
        )
        print(f"Fixed: Current Version {line.group(2)} -> {version} ({phase})")
        return 0
    print(
        f"FAIL: ROADMAP.md says Current Version {line.group(2)}, but the phase in "
        f"progress is {phase}, whose Target Release is {version}.\n"
        "  The current phase is the first one whose 'Phase exit gate' item is not\n"
        "  ticked.  Fix the line with:  make roadmap-version-fix"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
