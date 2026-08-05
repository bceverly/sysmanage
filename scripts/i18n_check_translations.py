#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Deterministic translation-quality gates for CI (no LLM required).

Two checks, runnable independently so one can land in CI before the
other:

  --placeholders   Every translated value must carry EXACTLY the same
                   interpolation tokens ({{var}}, {var}, %s, %d,
                   %(x)s, <tags>) as its English source.  This catches a
                   machine translator dropping or mangling a placeholder
                   — a real runtime bug.  SAFE TO ENABLE NOW: untranslated
                   ``[TODO] <english>`` values still carry the source
                   placeholders, so they pass.

                   Covers BOTH catalogs: the frontend JSON locales and
                   the backend gettext ``.po`` catalogs.  It used to
                   check only the frontend, and the backend catalogs
                   quietly accumulated the exact bug this gate exists to
                   stop — four entries where the translator had emitted a
                   SECOND ``%s`` that the msgid does not have, e.g.
                   ``"Marked message as processing: %s"`` translated to
                   ``"메시지 '%s'를 처리 중으로 변경했습니다: %s"``.  Every one
                   of those raises ``TypeError: not enough arguments for
                   format string`` the moment that log line runs in that
                   locale, and the gate reported "integrity holds".

  --completeness   No ``[TODO] `` placeholders remain in any non-English
                   locale.  Enable this in CI once the translation pass
                   (``make i18n-translate`` on the local model) is done;
                   until then it will (correctly) fail.

Default: run both.  Exit non-zero on any failure.  Pure stdlib — no
network, deterministic, CI-friendly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "frontend" / "public" / "locales"
PO_LOCALES_DIR = REPO_ROOT / "backend" / "i18n" / "locales"
TODO_PREFIX = "[TODO] "
EN = "en"

_PLACEHOLDER_RE = re.compile(r"(\{\{[^}]+\}\}|\{[^}]+\}|%\([^)]+\)[sd]|%[sd]|<[^>]+>)")


def _placeholders(text: str):
    return sorted(_PLACEHOLDER_RE.findall(text))


def _flatten(node, prefix=""):
    out = {}
    if isinstance(node, dict):
        for key, val in node.items():
            out.update(_flatten(val, f"{prefix}{key}." if prefix else f"{key}."))
    elif isinstance(node, str):
        out[prefix.rstrip(".")] = node
    return out


def _load(lang):
    path = LOCALES_DIR / lang / "translation.json"
    if not path.exists():
        return {}
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _langs():
    return sorted(p.name for p in LOCALES_DIR.iterdir() if p.is_dir() and p.name != EN)


# --- backend gettext catalogs -------------------------------------------------
#
# The .po format is line-oriented and the only shapes gettext emits here are a
# single quoted string or a leading ``""`` followed by continuation lines, so a
# small reader beats adding a dependency.  It intentionally reads the msgid as
# the English source rather than trusting an en catalog: gettext's source of
# truth IS the msgid.

_PO_DIRECTIVE = re.compile(r'^(msgid|msgstr)\s+"(.*)"\s*$')
_PO_CONTINUATION = re.compile(r'^"(.*)"\s*$')


def _po_unescape(text: str) -> str:
    return text.replace(r"\"", '"').replace(r"\n", "\n").replace(r"\\", "\\")


def _load_po(path: Path):
    """{msgid: msgstr} for every entry with a non-empty translation."""
    entries, key, buf, field = {}, None, [], None

    def flush():
        if field == "msgstr" and key:
            value = _po_unescape("".join(buf))
            if value:
                entries[key] = value

    for raw in path.read_text(encoding="utf-8").split("\n"):
        line = raw.strip()
        directive = _PO_DIRECTIVE.match(line)
        if directive:
            name, first = directive.groups()
            if name == "msgid":
                flush()
                field, buf = "msgid", [first]
            else:
                key = _po_unescape("".join(buf))
                field, buf = "msgstr", [first]
            continue
        continuation = _PO_CONTINUATION.match(line)
        if continuation and field:
            buf.append(continuation.group(1))
            continue
        # A blank line or comment ends the entry.
        flush()
        field, buf = None, []
    flush()
    entries.pop("", None)  # the catalog header
    return entries


def _po_langs():
    if not PO_LOCALES_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in PO_LOCALES_DIR.iterdir()
        if p.is_dir() and p.name != EN and any(p.glob("LC_MESSAGES/*.po"))
    )


def check_po_placeholders() -> int:
    """Same rule as the JSON pass, applied to the gettext catalogs."""
    failures = 0
    for lang in _po_langs():
        for path in sorted((PO_LOCALES_DIR / lang / "LC_MESSAGES").glob("*.po")):
            for msgid, msgstr in _load_po(path).items():
                if msgstr.startswith(TODO_PREFIX):
                    continue
                if _placeholders(msgid) != _placeholders(msgstr):
                    failures += 1
                    print(
                        f"  {lang}: placeholder mismatch in {path.name}\n"
                        f"      msgid : {_placeholders(msgid)}  {msgid!r}\n"
                        f"      {lang:6}: {_placeholders(msgstr)}  {msgstr!r}",
                        file=sys.stderr,
                    )
    return failures


def check_completeness() -> int:
    failures = 0
    for lang in _langs():
        todos = [k for k, v in _load(lang).items() if v.startswith(TODO_PREFIX)]
        if todos:
            failures += len(todos)
            print(f"  {lang}: {len(todos)} untranslated [TODO] keys", file=sys.stderr)
            for k in todos[:5]:
                print(f"      - {k}", file=sys.stderr)
            if len(todos) > 5:
                print(f"      ... and {len(todos) - 5} more", file=sys.stderr)
    if failures:
        print(f"FAIL: {failures} untranslated key(s) remain", file=sys.stderr)
    else:
        print("OK: every non-English key is translated")
    return 1 if failures else 0


def check_placeholders() -> int:
    en = _load(EN)
    failures = 0
    for lang in _langs():
        loc = _load(lang)
        for key, src in en.items():
            tgt = loc.get(key)
            if tgt is None or tgt.startswith(TODO_PREFIX):
                continue  # missing handled by i18n-validate; TODO is pre-translation
            if _placeholders(src) != _placeholders(tgt):
                failures += 1
                print(
                    f"  {lang}: placeholder mismatch at '{key}'\n"
                    f"      en : {_placeholders(src)}\n"
                    f"      {lang:3}: {_placeholders(tgt)}",
                    file=sys.stderr,
                )
    failures += check_po_placeholders()
    if failures:
        print(f"FAIL: {failures} placeholder mismatch(es)", file=sys.stderr)
    else:
        print(
            "OK: placeholder integrity holds across all locales "
            "(frontend JSON + backend .po)"
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--completeness", action="store_true")
    parser.add_argument("--placeholders", action="store_true")
    args = parser.parse_args()
    run_both = not (args.completeness or args.placeholders)

    rc = 0
    if args.placeholders or run_both:
        rc |= check_placeholders()
    if args.completeness or run_both:
        rc |= check_completeness()
    return rc


if __name__ == "__main__":
    sys.exit(main())
