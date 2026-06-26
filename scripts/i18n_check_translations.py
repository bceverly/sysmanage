#!/usr/bin/env python3
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
    if failures:
        print(f"FAIL: {failures} placeholder mismatch(es)", file=sys.stderr)
    else:
        print("OK: placeholder integrity holds across all locales")
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
