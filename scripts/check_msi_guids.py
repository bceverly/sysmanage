#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Gate: every WiX Component needs its own GUID.

WHY THIS EXISTS
---------------
WiX identifies a component by its GUID, so two components sharing one is an
error (WIX0369) and the MSI does not build.  The failure mode is nasty in a
specific way: the GUIDs in this file are hand-authored and follow a visual
pattern (``A7B8C9D0-...``, ``B8C9D0E1-...``), so the obvious way to add a new
component -- copy a neighbour and advance the pattern -- lands on a value used
further down the file.  That is exactly what happened on 2026-08-18: two new
nginx components collided with ``NssmExecutable`` and ``SbomBackend``, and it
surfaced only in CI, after a full release build on both architectures.

Nothing else catches it.  The file is valid XML either way, so an XML check
passes; the collision is only meaningful to WiX, and WiX runs on Windows.  This
check is a dozen lines and runs anywhere, so the mistake is caught at lint time
on any platform instead of costing a release cycle.

    python3 scripts/check_msi_guids.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WXS_FILES = sorted(REPO.glob("installer/**/*.wxs"))

COMPONENT_RE = re.compile(
    r'<Component\s+Id="(?P<id>[^"]+)"\s+Guid="\{?(?P<guid>[0-9A-Fa-f-]+)\}?"'
)
# A GUID that is all-zeros, or obviously a placeholder, is as broken as a
# duplicate -- WiX accepts it and every install then shares component identity.
PLACEHOLDER = {"00000000-0000-0000-0000-000000000000"}


def check_file(path: Path) -> list:
    problems = []
    text = path.read_text(encoding="utf-8")
    by_guid = defaultdict(list)
    for match in COMPONENT_RE.finditer(text):
        guid = match.group("guid").upper()
        by_guid[guid].append(match.group("id"))

    if not by_guid:
        return [f"{path.relative_to(REPO)}: no <Component> elements found"]

    for guid, ids in sorted(by_guid.items()):
        if len(ids) > 1:
            problems.append(
                f"{path.relative_to(REPO)}: GUID {guid} is shared by "
                f"{len(ids)} components: {', '.join(sorted(ids))}"
            )
        if guid.lower() in PLACEHOLDER:
            problems.append(
                f"{path.relative_to(REPO)}: placeholder GUID {guid} "
                f"on {', '.join(sorted(ids))}"
            )
    return problems


def main() -> int:
    if not WXS_FILES:
        print("[skip] no .wxs files found")
        return 0

    problems = []
    total = 0
    for path in WXS_FILES:
        text = path.read_text(encoding="utf-8")
        total += len(COMPONENT_RE.findall(text))
        problems.extend(check_file(path))

    if problems:
        print(
            f"FAIL: {len(problems)} WiX component GUID problem(s).\n"
            "WiX rejects duplicate component GUIDs (WIX0369) and the MSI will "
            "not build.\n"
            "Generate a fresh one -- do NOT copy a neighbour and advance the "
            "pattern, which is\n"
            "how the last collision happened:\n"
            '    python3 -c "import uuid; print(str(uuid.uuid4()).upper())"\n',
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"[OK] all {total} WiX component GUID(s) unique across "
        f"{len(WXS_FILES)} file(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
