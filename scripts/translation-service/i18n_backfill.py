#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
i18n_backfill.py — idempotent translation-backfill client for the SysManage
translation service (``translate_service.py``).

Walks a locale store, finds the strings that are NOT yet translated (only the
gaps), batch-translates them through the service, and writes them back into the
existing i18n files.  Scoped to THIS repo's own locale stores only — it never
reaches into a sibling repository (docs / proplus / agent translate themselves
via their own ``scripts/translate_i18n.py``):

  frontend  frontend/public/locales/<lang>/translation.json            (JSON)
  backend   backend/i18n/locales/<lang>/LC_MESSAGES/messages.po        (.po)

Key properties:
  * IDEMPOTENT — only untranslated entries are sent.  JSON gaps are ``[TODO] …``
    placeholders or missing keys; ``.po`` gaps are empty ``msgstr``.  Already
    translated strings are never re-sent, so re-running is cheap and resumable.
  * CONSERVATIVE — if the service returns the English source for a string (its
    placeholder-integrity guard could not safely translate it), that entry is
    LEFT as a gap rather than written as English, so a later run retries it.
  * DEDUPED — identical English strings are translated once per language.
  * BATCHED — one request per chunk (``--client-batch``) per language.

Usage:
  # service on the beast box:
  python3 i18n_backfill.py --project frontend --service http://beast:8765
  python3 i18n_backfill.py --project backend  --service http://beast:8765

  # preview only, no writes / no service calls:
  python3 i18n_backfill.py --project frontend --dry-run

  # offline completeness gate (CI / release): no service, no writes:
  python3 i18n_backfill.py --project frontend --check

Options:
  --project {frontend,backend}   which of THIS repo's locale stores
  --root PATH        sysmanage repo root (default: auto-detected from this file)
  --service URL      service base URL (default env TRANSLATION_SERVICE_URL or
                     http://localhost:8765)
  --langs a,b,c      restrict to these locale codes (default: all 13 targets)
  --client-batch N   strings per HTTP request (default 100)
  --limit N          translate at most N gaps per language (smoke testing)
  --dry-run          report gaps; do not call the service or write files
  --check            offline gate: fail non-zero if any gap remains (no service)

The ``.po`` driver needs ``polib`` (pip install polib).  JSON needs nothing
beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# The 13 translation targets (English is the source, never a target).
TARGET_LANGS = [
    "ar",
    "de",
    "es",
    "fr",
    "hi",
    "it",
    "ja",
    "ko",
    "nl",
    "pt",
    "ru",
    "zh_CN",
    "zh_TW",
]

# A string with no letters (pure placeholder/code/punctuation) is correct to
# leave unchanged; the conservative write rule uses this to tell "legitimately
# identical" from "service fell back to English because it couldn't translate".
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# Placeholder/markup tokens — used to distinguish a placeholder-fallback
# (identical output because the service couldn't translate a {{…}}/%s/<tag>
# safely) from a legitimately-identical term (acronyms like URL/IPv4 or words
# the model keeps as-is, e.g. "Details"). Only the former is held back to retry.
_PLACEHOLDER_RE = re.compile(
    r"\{\{.*?\}\}|\$\{[^}]+\}|\{[^{}]*\}|%\d+\$[sdfgex]|%\(\w+\)[sdfgexr]"
    r"|%[sdfgexr%]|\$[A-Za-z_]\w*|</?[A-Za-z][^>]*>|&[a-zA-Z]+;|&#\d+;"
)

# project -> (format, repo-relative-path, per-language file template)
#   {lang} in the template is replaced with the locale code.
# THIS repo's own locale stores only.  Paths are relative to the sysmanage repo
# root — intentionally NOT sibling-repo paths, so this client can never reach
# into another repository.  docs / proplus / agent each translate themselves via
# their own self-contained scripts/translate_i18n.py.
PRESETS: Dict[str, Tuple[str, str, str]] = {
    "frontend": ("json", "frontend/public/locales", "{lang}/translation.json"),
    "backend": ("po", "backend/i18n/locales", "{lang}/LC_MESSAGES/messages.po"),
}


# ---------------------------------------------------------------------------
# Service client
# ---------------------------------------------------------------------------


def _post(url: str, payload: dict, timeout: float = 1800.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    # nosemgrep: dynamic-urllib-use-detected -- service URL is operator config (trusted LAN), not request input
    with urllib.request.urlopen(
        req, timeout=timeout
    ) as resp:  # noqa: S310 (trusted LAN)
        return json.loads(resp.read().decode("utf-8"))


def _service_ok(service: str) -> bool:
    """True iff the translation service answers /health."""
    try:
        # nosemgrep: dynamic-urllib-use-detected -- service URL is operator config (trusted LAN), not request input
        with urllib.request.urlopen(  # noqa: S310 (trusted LAN)
            f"{service.rstrip('/')}/health", timeout=10
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def translate_to(
    service: str, texts: List[str], lang: str, client_batch: int
) -> List[str]:
    """Translate ``texts`` into a single ``lang``, aligned with the input."""
    out: List[str] = []
    for i in range(0, len(texts), client_batch):
        chunk = texts[i : i + client_batch]
        try:
            resp = _post(
                f"{service.rstrip('/')}/translate/batch",
                {"texts": chunk, "targets": [lang], "require_change": True},
                # We already filtered our intentionally-English strings
                # through i18n-allow.txt, so anything still here MUST
                # change; identical output is a failure, not a result.
            )
        except (urllib.error.URLError, OSError) as exc:
            sys.exit(
                f"\nERROR: lost connection to the translation service at {service}: {exc}\n"
                "  Already-finished languages are saved; re-run to resume."
            )
        for item in resp["results"]:
            # Take the service's OWN verdict rather than inferring one by
            # comparing output to input.  Comparing cannot distinguish "the
            # model legitimately kept this as-is" (IPv4, FQDN) from "the
            # service gave up and returned the English", which is why such
            # strings used to be re-sent over the network forever.
            # An older service omits "status"; assume ok so this still works.
            status = (item.get("status") or {}).get(lang, "ok")
            out.append((item["translations"][lang], status == "ok"))
        print(f"      …{min(i + client_batch, len(texts))}/{len(texts)}", flush=True)
    return out


def _flatten(obj: dict, prefix: str = "") -> Dict[str, str]:
    flat: Dict[str, str] = {}
    for key, val in obj.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            flat.update(_flatten(val, dotted))
        elif isinstance(val, str):
            flat[dotted] = val
    return flat


def _set_dotted(obj: dict, dotted: str, value: str) -> None:
    cur = obj
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _is_json_gap(value: Optional[str]) -> bool:
    return value is None or (isinstance(value, str) and value.startswith("[TODO]"))


# --- allow-list --------------------------------------------------------------
# Shared with scripts/i18n_strict.py so the translate pass and the gate agree on
# which values may legitimately stay English.  Without this the pass re-sends
# every proper noun on every run.
def _allow():
    """Load and return the i18n_strict module, or die trying.

    Returning None here silently disabled the allow-list for the WHOLE pass.
    On 2026-08-05 this resolver probed ``scripts/scripts/i18n_strict.py`` (the
    parent was already ``scripts/``), found nothing, and fell back to None — so
    every intentionally-English value was re-sent to the service on every run
    AND counted as a permanent gap by ``--check``, while ``i18n_strict.py``,
    which reads the same list correctly, reported OK.  Two gates, two answers,
    no error message anywhere.  An unresolvable allow-list means a broken
    checkout, not a soft condition: fail loudly instead of degrading.
    """
    import importlib.util  # noqa: PLC0415

    here = Path(__file__).resolve().parent
    tried = []
    for base in (here, *list(here.parents)[:3]):
        cand = base / "i18n_strict.py"
        tried.append(cand)
        if cand.exists():
            spec = importlib.util.spec_from_file_location("_i18n_strict", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit(
        "FATAL: cannot locate i18n_strict.py, the shared i18n-allow.txt "
        "reader.\n  Looked in:\n"
        + "".join(f"    {p}\n" for p in tried)
        + "  Without it every intentionally-English value is re-translated on\n"
        "  every run and reported as an unfixable gap.  Run from a full checkout."
    )


_STRICT = _allow()  # the i18n_strict module itself
_ALLOW = _STRICT.Allow(_STRICT.ALLOW_FILE)

# Anchored on __file__, not cwd, so `make translate` works from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))
# pylint: disable=wrong-import-position  # import must follow the sys.path insert
from i18n_hashes import record_translated  # noqa: E402


def _needs_translation(key: str, en_src: str, value, lang: str) -> bool:
    """True if this leaf still needs the service.

    A gap ([TODO]/missing/empty) OR a value left byte-identical to the English.
    The second half is the whole point: `make translate` used to look ONLY for
    gaps, so a string that came back English once was invisible to every
    subsequent run and stayed English forever.  There is deliberately NO
    minimum length — a short label is as user-facing as a paragraph, and a
    length floor is an invisible exemption nobody reviews.  Values that should
    stay English belong in i18n-allow.txt, where the decision is explicit.
    """
    if _is_json_gap(value):
        return True
    if not isinstance(value, str) or value != en_src:
        return False
    if _ALLOW is not None and _ALLOW.allows(key, en_src, lang):
        return False
    # ONE definition of "translatable", shared with i18n_strict.is_prose.
    # Keeping a second, looser test here (any letter) is what left
    # "https://grafana.example.com" as a permanent gap the strict gate did not
    # even consider a string: the pass demanded a translation the gate never
    # wanted.  Diverging predicates are how these two tools disagree.
    return bool(_STRICT.is_prose(en_src))


# NO client-side retry passes.  The service retries a bad reply ITSELF, next to
# the model, and then reports the outcome per string via ``status``.  Re-sending
# from here was pure waste: a LAN round-trip to ask the same model the same
# question, driven by a guess ("the output equals the input, so it must have
# failed") that is wrong for every term whose correct translation IS the
# English — which is exactly how {{seconds}}s and `pkg_info stderr: %s` looped
# forever.


def _translate_uniq(
    service: str, uniq: List[str], lang: str, client_batch: int
) -> Dict[str, str]:
    """``{source: translation}`` for the strings the service translated.

    Sources the service reports as a fallback are omitted, so the caller leaves
    them as gaps for a later pass — no re-request from here.
    """
    resolved: Dict[str, str] = {}
    for src, (text, ok) in zip(uniq, translate_to(service, uniq, lang, client_batch)):
        if ok:
            resolved[src] = text
    return resolved


def run_json(
    base: Path,
    template: str,
    langs: List[str],
    service: Optional[str],
    client_batch: int,
    limit: Optional[int],
) -> None:
    en_path = base / template.format(lang="en")
    if not en_path.exists():
        sys.exit(f"ERROR: source file not found: {en_path}")
    en_flat = _flatten(json.loads(en_path.read_text(encoding="utf-8")))

    # Staleness-sidecar bookkeeping.  Collected across ALL locales because the
    # sidecar is per KEY, not per key-per-language: recording a key after
    # translating only some locales would hide the untranslated ones from the
    # stale check.  See i18n_hashes for the full rule.
    translated_keys: set = set()
    locale_flats: Dict[str, Dict[str, str]] = {}

    for lang in langs:
        path = base / template.format(lang=lang)
        if not path.exists():
            print(f"  {lang}: file missing ({path}) — skipped", flush=True)
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        lang_flat = _flatten(doc)

        # Self-heal allow-listed gaps.  A value flagged intentionally-English in
        # i18n-allow.txt is deliberately never sent to the service, so if it is
        # sitting as a [TODO] (or was requeued into one) that placeholder can
        # never be cleared and the gate can never close.  Resolve it to its
        # intended final value — plain English — up front.
        if service is not None and _ALLOW is not None:
            healed = 0
            for key, en_src in en_flat.items():
                if _ALLOW.allows(key, en_src, lang) and _is_json_gap(
                    lang_flat.get(key)
                ):
                    _set_dotted(doc, key, en_src)
                    healed += 1
            if healed:
                lang_flat = _flatten(doc)
                path.write_text(
                    json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(
                    f"  {lang}: resolved {healed} intentionally-English leaf/leaves",
                    flush=True,
                )

        # Gather (key, english) for every gap in this language.
        gaps: List[Tuple[str, str]] = [
            (key, en_src)
            for key, en_src in en_flat.items()
            if _needs_translation(key, en_src, lang_flat.get(key), lang)
        ]
        if limit:
            gaps = gaps[:limit]
        print(f"  {lang}: {len(gaps)} gap(s)", flush=True)
        if not gaps or service is None:
            continue

        # Dedup identical English strings; translate once each (with retry).
        uniq = sorted({src for _, src in gaps})
        translations = _translate_uniq(service, uniq, lang, client_batch)

        wrote = skipped = 0
        for key, en_src in gaps:
            cand = translations.get(en_src)
            if cand is not None:
                _set_dotted(doc, key, cand)
                translated_keys.add(key)
                wrote += 1
            else:
                skipped += 1
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        locale_flats[lang] = _flatten(doc)
        print(f"  {lang}: wrote {wrote}, left {skipped} gap(s) for retry", flush=True)

    # Record the English these translations were made FROM, so i18n_strict can
    # tell a later English edit from a current translation.  Doing it here --
    # as a byproduct of translating -- is what stops the requeue/translate/
    # still-stale loop and stops new keys shipping unprotected.  Only keys
    # written above, and only where no locale still has a gap.
    recorded = record_translated(base, en_flat, locale_flats, translated_keys)
    if recorded:
        print(f"  recorded {recorded} source hash(es) for staleness", flush=True)


# ---------------------------------------------------------------------------
# gettext .po driver  (empty msgstr = gap)
# ---------------------------------------------------------------------------


def run_po(
    base: Path,
    template: str,
    langs: List[str],
    service: Optional[str],
    client_batch: int,
    limit: Optional[int],
) -> None:
    try:
        import polib  # noqa: PLC0415
    except ImportError:
        sys.exit("ERROR: the .po driver needs polib — run: pip install polib")

    for lang in langs:
        path = base / template.format(lang=lang)
        if not path.exists():
            print(f"  {lang}: file missing ({path}) — skipped", flush=True)
            continue
        po = polib.pofile(str(path))
        # Gap = a real message with an empty translation (skip header + obsolete).
        # Same self-heal for gettext: an allow-listed msgid with an empty
        # msgstr can never be filled by the service (we never send it), so it
        # would stay a permanent gap.  Its intended value IS the msgid.
        if service is not None and _ALLOW is not None:
            healed = 0
            for entry in po:
                if (
                    entry.msgid
                    and not entry.obsolete
                    and not entry.msgstr
                    and _ALLOW.allows(entry.msgid, entry.msgid, lang)
                ):
                    entry.msgstr = entry.msgid
                    healed += 1
            if healed:
                po.save(str(path))
                print(
                    f"  {lang}: resolved {healed} intentionally-English msgid(s)",
                    flush=True,
                )

        # Empty msgstr OR one left identical to the msgid — the latter was
        # invisible to every previous run, so it stayed English forever.
        gap_entries = [
            e
            for e in po
            if e.msgid
            and not e.obsolete
            and (
                not e.msgstr
                or (
                    e.msgstr == e.msgid
                    and _HAS_LETTER.search(e.msgid)
                    and not (
                        _ALLOW is not None and _ALLOW.allows(e.msgid, e.msgid, lang)
                    )
                )
            )
        ]
        if limit:
            gap_entries = gap_entries[:limit]
        print(f"  {lang}: {len(gap_entries)} gap(s)", flush=True)
        if not gap_entries or service is None:
            continue

        uniq = sorted({e.msgid for e in gap_entries})
        translations = _translate_uniq(service, uniq, lang, client_batch)

        wrote = skipped = 0
        for e in gap_entries:
            cand = translations.get(e.msgid)
            if cand is not None:
                e.msgstr = cand
                wrote += 1
            else:
                skipped += 1
        po.save(str(path))
        print(f"  {lang}: wrote {wrote}, left {skipped} gap(s) for retry", flush=True)


# ---------------------------------------------------------------------------
# Completeness gate  (fail loudly if any locale is still untranslated)
# ---------------------------------------------------------------------------


def scan_gaps(
    base: Path, template: str, langs: List[str], fmt: str
) -> Dict[str, List[str]]:
    """Re-read the locale files on disk and return {lang: [untranslated keys]}.

    Authoritative — reads what was actually written, so it reflects strings the
    service held back (placeholder fallbacks) as well as any never filled."""
    result: Dict[str, List[str]] = {}
    if fmt == "json":
        en_flat = _flatten(
            json.loads((base / template.format(lang="en")).read_text(encoding="utf-8"))
        )
        for lang in langs:
            path = base / template.format(lang=lang)
            if not path.exists():
                result[lang] = ["<file missing>"]
                continue
            lf = _flatten(json.loads(path.read_text(encoding="utf-8")))
            # SAME definition the pass uses.  Counting only [TODO]/missing
            # here is how the run could print 'left 71 gap(s)' and then
            # '0 untranslated gaps' in the same breath.
            result[lang] = [
                k
                for k, en_src in en_flat.items()
                if _needs_translation(k, en_src, lf.get(k), lang)
            ]
    else:
        import polib  # noqa: PLC0415

        for lang in langs:
            path = base / template.format(lang=lang)
            if not path.exists():
                result[lang] = ["<file missing>"]
                continue
            po = polib.pofile(str(path))
            result[lang] = [
                e.msgid
                for e in po
                if e.msgid
                and not e.obsolete
                and (
                    not e.msgstr
                    or (
                        e.msgstr == e.msgid
                        and _HAS_LETTER.search(e.msgid)
                        and not (
                            _ALLOW is not None and _ALLOW.allows(e.msgid, e.msgid, lang)
                        )
                    )
                )
            ]
    return result


def enforce_no_gaps(
    project: str, base: Path, template: str, langs: List[str], fmt: str
) -> None:
    """Exit NON-ZERO, loudly, if any locale still has untranslated strings.

    Wired into ``make translate`` so an incomplete locale set fails the build
    instead of quietly sliding through — translations must be 100%."""
    offenders = {l: ks for l, ks in scan_gaps(base, template, langs, fmt).items() if ks}
    if not offenders:
        print(
            f"[OK] {project}: 0 untranslated gaps in {len(langs)} locale(s).\n"
            "  (Gaps only — this does NOT check translation QUALITY.  Run\n"
            "   `make i18n-strict` for English-identical / stale / wrong-language.)",
            flush=True,
        )
        return
    total = sum(len(ks) for ks in offenders.values())
    sep = "=" * 72
    lines = [
        "",
        sep,
        f"  ✗✗✗  TRANSLATION INCOMPLETE — {project}: {total} untranslated string(s) "
        f"in {len(offenders)} locale(s)  ✗✗✗",
        sep,
    ]
    for lang in sorted(offenders):
        ks = offenders[lang]
        sample = ", ".join(ks[:4]) + (" …" if len(ks) > 4 else "")
        lines.append(f"    {lang}: {len(ks):>5} gap(s)   {sample}")
    lines += [
        sep,
        "  These locales still have untranslated gaps.  Fill them with:",
        "      make translate SERVICE=http://<gpu-box>:8765",
        "  or translate the remaining keys by hand.  Locales must be 100%.",
        sep,
        "",
    ]
    print("\n".join(lines), file=sys.stderr, flush=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--project", required=True, choices=sorted(PRESETS))
    ap.add_argument(
        "--root", default=None, help="sysmanage repo root (default: auto-detected)"
    )
    ap.add_argument(
        "--service",
        default=os.getenv("TRANSLATION_SERVICE_URL", "http://localhost:8765"),
    )
    ap.add_argument("--langs", default=None, help="comma-separated locale subset")
    ap.add_argument("--client-batch", type=int, default=100)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--fail-on-gaps",
        action="store_true",
        help="after the run, exit non-zero (loudly) if any locale still has gaps",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="offline completeness gate: scan locales and exit non-zero if any gap "
        "remains. NO service calls, NO writes — safe for CI / release hooks.",
    )
    args = ap.parse_args()

    fmt, rel, template = PRESETS[args.project]

    # Default --root = THIS repo's own root (scripts/translation-service/ is two
    # levels down), so every preset path stays inside the sysmanage repo and the
    # client can never write into a sibling repository.
    root = Path(args.root) if args.root else Path(__file__).resolve().parents[2]
    base = root / rel
    if not base.exists():
        sys.exit(
            f"ERROR: locale dir not found: {base}\n  (is this the sysmanage repo root?)"
        )

    langs = (
        [x.strip() for x in args.langs.split(",") if x.strip()]
        if args.langs
        else TARGET_LANGS
    )
    service = None if args.dry_run else args.service

    print(f"project={args.project} format={fmt} base={base}", flush=True)

    # Offline completeness gate — no service, no writes.  Scans the files on
    # disk and exits non-zero (loudly) if anything is still untranslated.
    if args.check:
        print("mode=check (offline — no service calls, no writes)", flush=True)
        enforce_no_gaps(args.project, base, template, langs, fmt)
        return

    print(f"service={service or '(dry-run)'} langs={langs}", flush=True)

    # Fail fast with a clear message if the service isn't reachable, rather than
    # grinding through gap detection and then dumping a urllib traceback.
    if service and not _service_ok(service):
        sys.exit(
            f"\nERROR: translation service not reachable at {service}\n"
            "  Is it running on the GPU box?  Point at it with one of:\n"
            "    make translate SERVICE=http://<beast>:8765\n"
            "    export TRANSLATION_SERVICE_URL=http://<beast>:8765\n"
            "  (the default is http://localhost:8765)."
        )

    if fmt == "json":
        run_json(base, template, langs, service, args.client_batch, args.limit)
    else:
        run_po(base, template, langs, service, args.client_batch, args.limit)

    print("done.", flush=True)

    # Final gate: make an incomplete locale set a hard, loud failure.
    if args.fail_on_gaps:
        enforce_no_gaps(args.project, base, template, langs, fmt)


if __name__ == "__main__":
    main()
