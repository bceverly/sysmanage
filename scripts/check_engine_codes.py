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
an issued license, which is what makes the license server serve it, which is
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
    TIER_FEATURES,
    TIER_MODULES,
    FeatureCode,
    LicenseTier,
    ModuleCode,
)

# The Pro+ repo, when it happens to be checked out beside this one. CI clones
# ONE repo, so its absence is not a failure -- the feature cross-check below
# simply does not run there, exactly as sync_i18n_tooling.py treats a missing
# sibling.
PROPLUS = REPO.parent / "sysmanage-professional-plus"

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


def _generator_text():
    path = PROPLUS / "backend" / "licensing" / "features.py"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _strings(block):
    """Quoted codes in a list block, comments stripped first (a comment may
    quote a code it is talking about)."""
    body = "\n".join(line.split("#", 1)[0] for line in block.splitlines())
    return set(re.findall(r'["\']([a-z0-9_]+)["\']', body))


def issued_by_tier(text):
    """{"professional": codes, "enterprise": codes} the generator issues.

    Both blocks: until 2026-11-14 only PROFESSIONAL_FEATURES was read, so
    the seven Enterprise-only codes the generator issues were never checked.
    """
    pro = re.search(r"^PROFESSIONAL_FEATURES\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    ent = re.search(
        r"^ENTERPRISE_FEATURES\s*=\s*PROFESSIONAL_FEATURES\s*\+\s*\[(.*?)^\]",
        text,
        re.S | re.M,
    )
    if not pro or not ent:
        return None
    professional = _strings(pro.group(1))
    return {
        "professional": professional,
        "enterprise": professional | _strings(ent.group(1)),
    }


def module_tiers(text):
    """{module code: tier} from the generator's MODULES dict."""
    block = re.search(r"^MODULES\s*=\s*\{(.*?)^\}", text, re.S | re.M)
    if not block:
        return {}
    return dict(
        re.findall(
            r'^    ["\']([a-z0-9_]+)["\']:\s*\{.*?["\']tier["\']:\s*["\']([a-z_]+)["\']',
            block.group(1),
            re.S | re.M,
        )
    )


def issued_feature_codes():
    """Feature strings the Pro+ generator can put in a license, or None.

    ``None`` means the sibling repo is not checked out here, which is the
    normal case in CI and not a failure.

    Read with a regex rather than by importing: the two repos have separate
    virtualenvs and separate ``backend`` packages, and importing the other
    one's would shadow this one's on ``sys.path``.
    """
    text = _generator_text()
    tiers = issued_by_tier(text) if text else None
    if not tiers:
        return None
    return tiers["enterprise"]


# Feature codes whose tier deliberately differs between the generator and
# TIER_FEATURES, each with the reason.  Empty since "api" moved to
# Professional to match the generator (2026-11-14); add an entry only with a
# reviewed reason.
TIER_EXCEPTIONS: dict = {}

_RANK = {"professional": 1, "enterprise": 2, "multitenant_saas": 3}
_OSS_TIER = {
    "professional": LicenseTier.PROFESSIONAL,
    "enterprise": LicenseTier.ENTERPRISE,
    "multitenant_saas": LicenseTier.MULTITENANT_SAAS,
}


def tier_disagreements(text):
    """Every code whose lowest tier differs between the two repos.

    A Professional license must not unlock an Enterprise capability, and a
    Professional TENANT edition (multi-tenancy gates each tenant by
    TIER_FEATURES / TIER_MODULES) must not be refused what a Professional
    license carries -- both follow from the two tables agreeing.
    """
    problems = []
    tiers = issued_by_tier(text) or {}
    for name in ("professional", "enterprise"):
        here = {f.value for f in TIER_FEATURES[_OSS_TIER[name]]}
        issued = tiers.get(name, set())
        for code in sorted((issued - here) | (here & tiers.get("enterprise", set()))
                           - issued):  # fmt: skip
            if code not in TIER_EXCEPTIONS:
                problems.append(f"feature {code!r}: tiers differ at {name}")
    for code, tier in sorted(module_tiers(text).items()):
        if code not in {m.value for m in ModuleCode}:
            continue  # reported by main() when dispatched
        for name, oss_tier in _OSS_TIER.items():
            entitled = _RANK[tier] <= _RANK[name]
            if entitled != (ModuleCode(code) in TIER_MODULES[oss_tier]):
                problems.append(
                    f"module {code!r}: generator tier {tier}, "
                    f"TIER_MODULES[{name}] disagrees"
                )
    return sorted(set(problems))


_GATED = (
    re.compile(r'feature_gate\(\s*["\']([a-z0-9_]+)["\']\s*\)'),
    re.compile(r'^\s*[A-Z_]*FEATURE\s*=\s*["\']([a-z0-9_]+)["\']', re.M),
)


def engine_gated_features():
    """{feature code: engine} for every feature an engine's routes gate on."""
    found = {}
    for path in sorted((PROPLUS / "module-source").glob("*/*.p[yx][xi]")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in _GATED:
            for code in pattern.findall(text):
                found.setdefault(code, path.parent.name)
    return found


def never_issued(text):
    """Features an engine gates on that no license can carry: the route is
    closed to every customer.  ``health_history`` was one until 2026-11-14 --
    the health engine's history route answered "license required" to every
    Professional and Enterprise license."""
    issued = (issued_by_tier(text) or {}).get("enterprise", set())
    return sorted(
        f"feature {code!r} gated by {engine} is never issued"
        for code, engine in engine_gated_features().items()
        if code not in issued
    )


def check_tiers():
    """Print and count every tier disagreement; 0 when the repos agree."""
    text = _generator_text()
    if text is None:
        return 0
    problems = tier_disagreements(text) + never_issued(text)
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        print(
            "\nThe license generator (sysmanage-professional-plus "
            "backend/licensing/features.py)\nand TIER_FEATURES / TIER_MODULES "
            "here must put each code in the same\nlowest tier.  Fix whichever "
            "side is wrong, or add a reviewed TIER_EXCEPTIONS entry.",
            file=sys.stderr,
        )
        return 1
    print("[OK] the license generator and TIER_FEATURES / TIER_MODULES agree")
    return 0


def check_features():
    """Every feature a license can carry must exist in FeatureCode.

    THE BUG THIS CATCHES is the sibling of the module one above, and it had
    already happened three times over before anyone looked: ``secrets``,
    ``containers`` and ``multiuser`` were issued in every Professional license
    and were absent from ``FeatureCode`` entirely, so ``FeatureCode(f)`` over a
    real license's features raised on a perfectly valid license. Nothing had
    done that yet, which is the only reason it never bit -- those capabilities
    are gated by their MODULES instead. A fourth one would have been just as
    invisible.

    Returns 0/1 like main(); prints its own diagnosis.
    """
    issued = issued_feature_codes()
    if issued is None:
        print(
            "[skip] feature cross-check: sysmanage-professional-plus is not "
            "checked out beside this repo"
        )
        return 0

    known = {f.value for f in FeatureCode}
    tiered = set()
    for features in TIER_FEATURES.values():
        tiered |= {f.value for f in features}

    unknown = sorted(issued - known)
    untiered = sorted((issued & known) - tiered)

    if unknown:
        print(
            "ERROR: features the license generator issues but MISSING from "
            "FeatureCode:",
            file=sys.stderr,
        )
        for code in unknown:
            print(f"  {code}", file=sys.stderr)
    if untiered:
        print(
            "ERROR: features in FeatureCode but in NO tier of TIER_FEATURES:",
            file=sys.stderr,
        )
        for code in untiered:
            print(f"  {code}", file=sys.stderr)

    if unknown or untiered:
        print(
            "\nA license carrying a feature this server cannot name is a "
            "license\nthis server cannot reason about: FeatureCode(value) "
            "raises on it.\nFix: add the code to FeatureCode and to the tier "
            "the Pro+ repo's\nPROFESSIONAL_FEATURES / ENTERPRISE_FEATURES "
            "list puts it in.",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] all {len(issued)} issuable feature code(s) are known and tiered")
    return 0


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
            "\nAn unregistered engine is never put in a license, so the license\n"
            "server never serves it, the runtime directory is never created, and\n"
            "the OSS shim answers 'requires a Professional+ license' forever.\n"
            "Fix: add the code to ModuleCode and to the tier named in the\n"
            'engine\'s own module-source/<code>/metadata.json "tier" field.',
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] all {len(referenced_codes())} dispatched engine code(s) "
        "are registered and licensable"
    )
    return check_features() or check_tiers()


if __name__ == "__main__":
    sys.exit(main())
