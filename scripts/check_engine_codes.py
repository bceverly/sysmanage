#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Gate: every Pro+ engine this code dispatches to must be licensable.

THE BUG THIS CATCHES
--------------------
The OSS server keeps thin shims that delegate to a Pro+ engine when it is
loaded::

    _ENGINE_CODE = "child_host_handlers_engine"
    engine = module_loader.get_module(_ENGINE_CODE)

For that engine to ever BE loaded it must also exist as a ``ModuleCode`` member
and appear in at least one tier of ``TIER_MODULES`` -- that is what puts it in
an issued licence, which is what makes the licence server serve it, which is
what creates the runtime directory the server loads from.

Miss the registration and nothing anywhere errors.  The engine builds, the
bundle publishes, ``install-modules-local.sh`` reports
"not installed on this server - skipped", ``get_module`` returns ``None``, and
the shim answers "requires a Professional+ license" on a server that HAS one.
Found 2026-08-12: ``child_host_handlers_engine`` had been built and dispatched
to since Phase 12.5 while being absent from both licensing registries.

The failure is invisible precisely because every individual piece behaves
correctly, so it needs a gate rather than a test of any one component.

WHAT IT DOES NOT CHECK
----------------------
The Pro+ half -- that the engine is in that repo's ``MODULES`` dict with a
matching tier -- is checked by its own repo's
``scripts/check_module_registry.py``.  Deliberately split: each gate runs with
only its own repository checked out, which is what CI has.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"

sys.path.insert(0, str(REPO))

# pylint: disable=wrong-import-position  # import must follow the sys.path insert
from backend.licensing.features import (  # noqa: E402
    TIER_MODULES,
    ModuleCode,
)

# ``module_loader.get_module("<code>")`` and the ``_ENGINE_CODE = "<code>"``
# constant the shims assign it to.  Both are string literals, so they can be
# read without importing every handler module.
_PATTERNS = (
    re.compile(r'get_module\(\s*["\']([a-z0-9_]+)["\']\s*\)'),
    re.compile(r'^_ENGINE_CODE\s*=\s*["\']([a-z0-9_]+)["\']', re.M),
    re.compile(r'^ENGINE_CODE\s*=\s*["\']([a-z0-9_]+)["\']', re.M),
)


def referenced_codes():
    """{engine code: [files that reference it]} across backend/."""
    found = {}
    for path in sorted(BACKEND.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _PATTERNS:
            for code in pattern.findall(text):
                found.setdefault(code, []).append(path.relative_to(REPO))
    return found


def licensed_codes():
    """Every module code that appears in at least one tier."""
    out = set()
    for modules in TIER_MODULES.values():
        out |= {m.value for m in modules}
    return out


def main():
    known = {m.value for m in ModuleCode}
    licensed = licensed_codes()

    unknown, unlicensed = [], []
    for code, files in sorted(referenced_codes().items()):
        where = ", ".join(str(f) for f in sorted(set(files))[:3])
        if code not in known:
            unknown.append((code, where))
        elif code not in licensed:
            unlicensed.append((code, where))

    if unknown:
        print(
            "ERROR: engine codes dispatched to but MISSING from ModuleCode:",
            file=sys.stderr,
        )
        for code, where in unknown:
            print(f"  {code:<34} referenced in {where}", file=sys.stderr)

    if unlicensed:
        print(
            "ERROR: engine codes in ModuleCode but in NO tier of TIER_MODULES:",
            file=sys.stderr,
        )
        for code, where in unlicensed:
            print(f"  {code:<34} referenced in {where}", file=sys.stderr)

    if unknown or unlicensed:
        print(
            "\nAn unregistered engine is never put in a licence, so the licence\n"
            "server never serves it, the runtime directory is never created, and\n"
            "the OSS shim answers 'requires a Professional+ license' forever.\n"
            "Fix: add the code to ModuleCode and to the tier named in the\n"
            "engine's own module-source/<code>/metadata.json \"tier\" field.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] all {len(referenced_codes())} dispatched engine code(s) "
        "are registered and licensable"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
