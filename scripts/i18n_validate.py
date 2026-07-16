#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""i18n extraction + validation pipeline for sysmanage frontend.

Modes (one required):
  --extract  Scan ``frontend/src/`` for ``t('key', 'English fallback')`` calls
             and emit a flat JSON of {key: en_fallback} to stdout.
  --validate Verify every key referenced in code exists in every locale
             JSON.  Exit non-zero on missing keys.  Lists orphaned
             (in-locale-but-not-in-code) keys as a warning.
  --seed     Like ``--validate`` but in seed mode: missing keys in
             non-English locales are filled with the English fallback
             prefixed by ``[TODO] ``, so a reviewer can grep and complete.
             Exits 0 even when seeding occurred.

Common to all three: walks the locale tree at
``frontend/public/locales/<lang>/translation.json``.

Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "frontend" / "src"
LOCALES_DIR = REPO_ROOT / "frontend" / "public" / "locales"

# Prefixes used in template-literal ``t(`prefix.${var}`)`` lookups — the
# regex extractor sees only the static prefix, so any nested key under one
# of these is "live" even if no static reference matches it.  Keep this
# list in sync with grep:
#   grep -ohE "t\(\`[a-zA-Z][a-zA-Z0-9._]*\.\\\${" frontend/src/**/*.tsx
DYNAMIC_KEY_PREFIXES = (
    "airgap.freshness.label.",  # Phase 11 B4 — t(`airgap.freshness.label.${label}`)
    "engine.",  # Phase 11 B7 — engine plan-description envelope: t(cmd.description_key, params)
    "hostDetail.hypervisor.state.",
    "maintenanceWindows.day.",  # Phase 14.2 — t(`maintenanceWindows.day.${d}`)
    "maintenanceWindows.state.",  # Phase 14.2 — t(`maintenanceWindows.state.${status.state}`)
    "nav.role.",  # Phase 11 — role chip uses t(`nav.role.${serverRole}`)
    "scripts.status.",
    "secrets.api_provider.",
    "secrets.certificate_type.",
    "secrets.cert_type.",
    "secrets.database_engine.",
    "secrets.key_type.",
    "secrets.type.",
)

# Match a JS string literal: ``"..."`` or ``'...'`` with backslash
# escapes.  Crucially, the OPPOSITE quote character is freely allowed
# inside — so the earlier ``[^'"\\]`` shape was wrong because it
# rejected apostrophes inside ``"don't"``.  Build the two forms
# separately and union them.
_DOUBLE_QUOTED = r'"(?:[^"\\]|\\.)*"'
_SINGLE_QUOTED = r"'(?:[^'\\]|\\.)*'"
_STRING_LITERAL = rf"(?:{_DOUBLE_QUOTED}|{_SINGLE_QUOTED})"
# Fallbacks are sometimes split with JS string concatenation
# (``"long line one " + "long line two"``) to keep individual literals
# under the line-length cap.  Match one or more literals joined by ``+``.
_CONCAT_STRING = rf"{_STRING_LITERAL}(?:\s*\+\s*{_STRING_LITERAL})*"

# Match ``t('key.path' [, 'English fallback'])`` — the fallback is
# optional because Pro+ tends to call ``t('login.title')`` without one
# (relying on en/ as the source of truth) while OSS calls
# ``t('mirror.add', 'Add Mirror')`` with the en value inline.  Both forms
# are valid; we extract the key in either case and capture the fallback
# only when present.  Ignores ``t(`template`)`` template literals — those
# need DYNAMIC_KEY_PREFIXES coverage instead.
T_CALL_WITH_FALLBACK = re.compile(
    rf"""\bt\(\s*['"]([\w.-]+)['"]\s*,\s*({_CONCAT_STRING})\s*[,)]""",
    re.MULTILINE,
)
# Permissive reference-only matcher: catches the key from any ``t('key',
# …)`` or ``t('key')`` call regardless of what the second argument looks
# like.  Used to mark keys as "referenced" even when the strict fallback
# regex can't parse the fallback expression (e.g., function-call
# fallbacks, complex template literals).  Note: ``[,)]`` here covers both
# one-arg and two-arg call shapes.
T_CALL_KEY_ONLY = re.compile(
    r"""\bt\(\s*['"]([\w.-]+)['"]\s*[,)]""",
    re.MULTILINE,
)

# Match a static template literal: backtick-delimited string with no
# ``${...}`` interpolation.  These behave like ordinary string fallbacks
# (e.g., ``t('key', `Some text`)``) and can be safely captured.
_PLAIN_TEMPLATE = r"`(?:[^`\\$]|\\.|\$(?!\{))*`"

# Match ``t('key', `static template`)`` for static template fallbacks.
T_CALL_TEMPLATE_FALLBACK = re.compile(
    rf"""\bt\(\s*['"]([\w.-]+)['"]\s*,\s*({_PLAIN_TEMPLATE})\s*[,)]""",
    re.MULTILINE,
)

# Match any template literal (with or without ``${...}`` interpolation)
# as a fallback.  Static text is extracted; ``${expr}`` segments are
# replaced with ``{{}}`` placeholders so the JSON value remains
# user-readable instead of containing raw JS expressions.  Used as a
# fallback when ``T_CALL_TEMPLATE_FALLBACK`` doesn't match.
_ANY_TEMPLATE = r"`(?:[^`\\]|\\.|\$\{[^}]*\})*`"
T_CALL_INTERP_TEMPLATE_FALLBACK = re.compile(
    rf"""\bt\(\s*['"]([\w.-]+)['"]\s*,\s*({_ANY_TEMPLATE})\s*[,)]""",
    re.MULTILINE,
)
_INTERP_EXPR = re.compile(r"\$\{[^}]*\}")

# Match ``t('key', { defaultValue: 'fallback', ...other options })`` — a
# common i18next idiom when the call also passes interpolation params.
# Restricted to single-line object literals to avoid back-tracking
# explosions; multi-line cases would need a real JS parser.
T_CALL_DEFAULTVALUE = re.compile(
    rf"""\bt\(\s*['"]([\w.-]+)['"]\s*,\s*\{{[^{{}}\n]*?defaultValue\s*:\s*({_STRING_LITERAL})""",
    re.MULTILINE,
)


def _decode_string_literal(literal: str) -> str:
    """Decode a single JS string literal (with surrounding quotes) into
    its runtime value.  Handles the common escapes (``\\n``, ``\\t``,
    quote-self, backslash-self)."""
    quote = literal[0]
    inner = literal[1:-1]
    # Order matters: unescape backslash last so we don't double-process
    # already-decoded escapes.
    inner = inner.replace(f"\\{quote}", quote)
    inner = inner.replace("\\n", "\n").replace("\\t", "\t")
    inner = inner.replace("\\\\", "\\")
    return inner


_STRING_LITERAL_RE = re.compile(_STRING_LITERAL)


def _decode_fallback(expr: str) -> str:
    """Decode a fallback expression (one literal or several joined by
    ``+``) into the final English string."""
    return "".join(
        _decode_string_literal(m.group(0)) for m in _STRING_LITERAL_RE.finditer(expr)
    )


def extract_keys() -> dict[str, str]:
    """Walk ``frontend/src/`` and return {key: english_fallback}."""
    keys: dict[str, str] = {}
    for path in SRC_DIR.rglob("*.tsx"):
        keys.update(_extract_from_file(path))
    for path in SRC_DIR.rglob("*.ts"):
        keys.update(_extract_from_file(path))
    return keys


def _extract_from_file(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return found
    # Two-arg form first — the fallback expression is the en authoritative
    # value.  The expression may be one literal, several literals joined
    # by ``+``, or contain the opposite quote character internally; the
    # decoder handles all three shapes.
    for match in T_CALL_WITH_FALLBACK.finditer(text):
        key, fallback_expr = match.group(1), match.group(2)
        fallback = _decode_fallback(fallback_expr)
        if key in found and found[key] != fallback:
            continue  # first writer wins on conflict
        found[key] = fallback
    # Static template-literal form: ``t('key', `Some text`)``.  Treated
    # identically to a plain string fallback once the backticks are
    # stripped.  Skipped silently for interpolated templates.
    for match in T_CALL_TEMPLATE_FALLBACK.finditer(text):
        key = match.group(1)
        if key in found and found[key]:
            continue
        literal = match.group(2)
        found[key] = literal[1:-1]  # strip surrounding backticks
    # ``defaultValue:`` option form: ``t('key', { defaultValue: '...' })``
    # — common when the call also passes interpolation params.
    for match in T_CALL_DEFAULTVALUE.finditer(text):
        key = match.group(1)
        if key in found and found[key]:
            continue
        found[key] = _decode_string_literal(match.group(2))
    # Interpolated template-literal fallback — last-resort extraction so
    # ``t('key', `Hello ${name}`)`` doesn't end up with no fallback at
    # all.  ``${expr}`` is rewritten to ``{{}}`` so the resulting string
    # is human-readable (and i18next-compatible enough that calling
    # interpolation with the right options would still work).
    for match in T_CALL_INTERP_TEMPLATE_FALLBACK.finditer(text):
        key = match.group(1)
        if key in found and found[key]:
            continue
        literal = match.group(2)[1:-1]  # strip surrounding backticks
        found[key] = _INTERP_EXPR.sub("{{}}", literal)
    # Permissive reference matcher for keys whose fallback expression the
    # strict regex couldn't capture (e.g., function-call fallbacks).  We
    # don't know the en value from source, so the seeder will leave an
    # empty placeholder when populating en.
    for match in T_CALL_KEY_ONLY.finditer(text):
        key = match.group(1)
        found.setdefault(key, "")
    return found


def flatten(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten a nested locale JSON into {dotted.key: leaf_value}."""
    out: dict[str, str] = {}
    for key, value in d.items():
        joined = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, joined))
        else:
            out[joined] = value
    return out


def insert_dotted(target: dict, dotted_key: str, value) -> None:
    """Insert ``value`` at ``dotted_key`` in ``target``.

    If a non-dict leaf already lives at an intermediate path (typical when a
    key was originally a label like ``auditLog.actionType: 'Action Type'``
    and the code later started referencing nested children like
    ``auditLog.actionType.create``), the leaf is replaced with a dict.
    The original leaf becomes orphaned — the validator's orphan list will
    surface it for cleanup if it's still needed under a renamed key.
    """
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        node = target.get(part)
        if not isinstance(node, dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def load_locale(lang: str) -> dict:
    path = LOCALES_DIR / lang / "translation.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_locale(lang: str, data: dict) -> None:
    path = LOCALES_DIR / lang / "translation.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def list_locales() -> list[str]:
    return sorted(p.name for p in LOCALES_DIR.iterdir() if p.is_dir())


def cmd_extract() -> int:
    keys = extract_keys()
    print(json.dumps(keys, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _delete_dotted(target: dict, dotted_key: str) -> bool:
    """Delete the leaf at ``dotted_key`` plus any newly-empty parent
    nodes.  Returns True if anything was removed."""
    parts = dotted_key.split(".")
    chain: list[tuple[dict, str]] = []
    node: object = target
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return False
        chain.append((node, part))
        node = node[part]
    # Remove leaf, then walk back up unwinding empty intermediate dicts.
    parent, key = chain[-1]
    del parent[key]
    for i in range(len(chain) - 2, -1, -1):
        upper, ukey = chain[i]
        child = upper[ukey]
        if isinstance(child, dict) and not child:
            del upper[ukey]
        else:
            break
    return True


def cmd_strip_orphans() -> int:
    """Delete keys that are present in locale JSONs but not referenced in
    code (and not under a dynamic prefix).  Operates on every locale
    consistently — a key is orphan only if no locale has a static-or-
    dynamic reference for it."""
    code_keys = set(extract_keys())
    removed_total = 0
    for lang in list_locales():
        data = load_locale(lang)
        flat = flatten(data)
        orphans = [
            k for k in (set(flat) - code_keys) if not _is_dynamic(k)
        ]
        if not orphans:
            continue
        for key in orphans:
            _delete_dotted(data, key)
        write_locale(lang, data)
        print(f"OK: {lang} pruned {len(orphans)} orphan keys", file=sys.stderr)
        removed_total += len(orphans)
    print(f"\nTotal orphans removed: {removed_total}", file=sys.stderr)
    return 0


def _is_dynamic(key: str) -> bool:
    return any(key.startswith(prefix) for prefix in DYNAMIC_KEY_PREFIXES)


def cmd_validate(seed: bool) -> int:
    code_keys = extract_keys()
    locales = list_locales()
    failures = 0
    for lang in locales:
        flat = flatten(load_locale(lang))
        missing = sorted(set(code_keys) - set(flat))
        # Dynamic-prefix keys are live even without a static reference.
        orphan = sorted(
            k for k in (set(flat) - set(code_keys)) if not _is_dynamic(k)
        )
        if missing:
            print(f"{lang}: {len(missing)} keys missing in locale", file=sys.stderr)
            for key in missing[:10]:
                print(f"  - {key}", file=sys.stderr)
            if len(missing) > 10:
                print(f"  ... and {len(missing) - 10} more", file=sys.stderr)
            if seed:
                data = load_locale(lang)
                for key in missing:
                    en_value = code_keys[key]
                    if en_value:
                        # Source code provided the en fallback inline — use it.
                        seeded = en_value if lang == "en" else f"[TODO] {en_value}"
                    else:
                        # Source code calls ``t('key')`` with no fallback string.
                        # Don't seed an empty string — Playwright + screen-reader
                        # accessibility queries (getByRole heading by name)
                        # render empty strings as nameless elements that cannot
                        # be located.  Use a visible placeholder instead so the
                        # gap surfaces during testing and translation review.
                        seeded = f"[MISSING:{key}]"
                    insert_dotted(data, key, seeded)
                write_locale(lang, data)
                print(f"  → seeded {len(missing)} keys", file=sys.stderr)
            else:
                failures += 1
        if orphan and not seed:
            # Phase 10 close-out (May 2026): orphans are a hard failure.
            # Run ``scripts/i18n_validate.py --strip-orphans`` to clean up.
            print(
                f"{lang} [FAIL]: {len(orphan)} orphan keys not referenced in code",
                file=sys.stderr,
            )
            for key in orphan[:10]:
                print(f"  - {key}", file=sys.stderr)
            if len(orphan) > 10:
                print(f"  ... and {len(orphan) - 10} more", file=sys.stderr)
            failures += 1
    if failures and not seed:
        print(
            f"\nFAIL: {failures} locale(s) have missing or orphan keys",
            file=sys.stderr,
        )
        # An "orphan" is a key in translation.json with no *static* t('...')
        # reference.  There are exactly two legitimate causes — spell out both so
        # this failure is self-service:
        print(
            "\nTo fix orphan keys, pick the cause:\n"
            "  1. The key is genuinely unused  -> remove it: "
            "python scripts/i18n_validate.py --strip-orphans\n"
            "  2. The key is looked up dynamically, e.g. "
            "t(`foo.bar.${x}`)  -> add its prefix ('foo.bar.') to "
            "DYNAMIC_KEY_PREFIXES near the top of scripts/i18n_validate.py\n"
            "(Missing keys, by contrast, are seeded with: make i18n-seed)",
            file=sys.stderr,
        )
        return 1
    print("\nOK: every code-referenced key exists in every locale", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extract", action="store_true")
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--seed", action="store_true")
    mode.add_argument("--strip-orphans", action="store_true")
    args = parser.parse_args()
    if args.extract:
        return cmd_extract()
    if args.strip_orphans:
        return cmd_strip_orphans()
    return cmd_validate(seed=args.seed)


if __name__ == "__main__":
    sys.exit(main())
