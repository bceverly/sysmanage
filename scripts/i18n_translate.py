#!/usr/bin/env python3
"""Machine-translate the [TODO]-seeded frontend locale strings.

Fills the ``[TODO] <English>`` placeholders that ``i18n_validate.py
--seed`` leaves in ``frontend/public/locales/<lang>/translation.json``
by calling a **local, OpenAI-compatible** chat endpoint (vLLM / Ollama /
llama.cpp / LM Studio — anything that speaks ``/v1/chat/completions``).
The actual translation runs on YOUR hardware; this script just moves
strings to and from it.

Config (env):
  I18N_LLM_BASE_URL   default http://localhost:11434/v1   (Ollama-style)
  I18N_LLM_MODEL      default qwen2.5:32b-instruct
  I18N_LLM_API_KEY    default "local" (most local servers ignore it)

Usage:
  python scripts/i18n_translate.py --lang all            # every non-en locale
  python scripts/i18n_translate.py --lang de --dry-run   # preview, no writes
  python scripts/i18n_translate.py --lang ja --limit 50  # cap strings/run

Safety / idempotency:
  * Only touches leaf values that begin with ``[TODO] ``.  Re-runs skip
    already-translated keys, so it's safe to resume after an interruption.
  * Placeholders ({{var}}, {var}, %s, %d, %(name)s) MUST survive
    translation verbatim; any string where they don't is left as
    [TODO] and reported, so a bad translation never silently ships.
  * English (``en``) is the source of truth and is never modified.
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

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "frontend" / "public" / "locales"

TODO_PREFIX = "[TODO] "

# Human-readable target language names (BCP-ish locale code -> name the
# model understands).  ``en`` is the source and never a target.
LANG_NAMES = {
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "ar": "Arabic",
    "zh_CN": "Simplified Chinese",
    "zh_TW": "Traditional Chinese",
}

# Tokens that must pass through translation untouched.
_PLACEHOLDER_RE = re.compile(r"(\{\{[^}]+\}\}|\{[^}]+\}|%\([^)]+\)[sd]|%[sd]|<[^>]+>)")


def _placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER_RE.findall(text))


def _walk_todos(node, path=()):
    """Yield (path_tuple, english_text) for every ``[TODO] ``-prefixed leaf."""
    if isinstance(node, dict):
        for key, val in node.items():
            yield from _walk_todos(val, path + (key,))
    elif isinstance(node, str) and node.startswith(TODO_PREFIX):
        yield path, node[len(TODO_PREFIX) :]


def _set_in(node, path, value):
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _endpoint() -> tuple[str, str, str]:
    base = os.environ.get("I18N_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    model = os.environ.get("I18N_LLM_MODEL", "qwen2.5:32b-instruct")
    key = os.environ.get("I18N_LLM_API_KEY", "local")
    return base, model, key


def _chat(base, model, key, system, user, timeout=120):
    """One OpenAI-compatible chat call; returns the assistant text."""
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # nosec B310 - operator-configured local URL
        f"{base}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    # Dev-only CLI tool; the endpoint is an operator-configured LLM URL
    # (I18N_LLM_BASE_URL), never request/user-derived — no SSRF surface.
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _translate_batch(base, model, key, lang_name, sources: list[str]) -> list[str]:
    """Translate a list of English UI strings; returns same-length list."""
    system = (
        "You are a professional software-UI translator. You translate "
        "short user-interface strings for a systems-management product. "
        "Keep translations concise and natural for buttons, labels, and "
        "messages. CRITICAL: preserve every placeholder token EXACTLY as "
        "given and untranslated — these include {{name}}, {count}, %s, "
        "%d, %(x)s, and HTML-like <tags>. Preserve leading/trailing "
        "punctuation and capitalization style. Respond with ONLY a JSON "
        "array of the translated strings, in the same order, and nothing "
        "else."
    )
    user = (
        f"Translate each of these UI strings into {lang_name}. "
        f"Return a JSON array of {len(sources)} strings.\n\n"
        + json.dumps(sources, ensure_ascii=False, indent=2)
    )
    text = _chat(base, model, key, system, user)
    # Tolerate a model that wraps the array in ```json fences or prose.
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("model did not return a JSON array")
    out = json.loads(match.group(0))
    if not isinstance(out, list) or len(out) != len(sources):
        raise ValueError(
            f"expected {len(sources)} translations, got "
            f"{len(out) if isinstance(out, list) else type(out).__name__}"
        )
    return [str(x) for x in out]


def translate_lang(lang: str, batch_size: int, limit: int, dry_run: bool) -> dict:
    path = LOCALES_DIR / lang / "translation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    todos = list(_walk_todos(data))
    if limit:
        todos = todos[:limit]
    stats = {"lang": lang, "todo": len(todos), "translated": 0, "skipped": 0}
    if not todos:
        return stats

    base, model, key = _endpoint()
    lang_name = LANG_NAMES.get(lang, lang)

    for start in range(0, len(todos), batch_size):
        chunk = todos[start : start + batch_size]
        sources = [eng for _path, eng in chunk]
        try:
            translations = _translate_batch(base, model, key, lang_name, sources)
        except (urllib.error.URLError, ValueError, KeyError, OSError) as exc:
            print(f"  [{lang}] batch @{start} failed: {exc}", file=sys.stderr)
            stats["skipped"] += len(chunk)
            continue
        for (path_tuple, english), translated in zip(chunk, translations):
            # Placeholder integrity gate: reject (leave as [TODO]) if the
            # model dropped or altered any interpolation token.
            if _placeholders(english) != _placeholders(translated):
                print(
                    f"  [{lang}] placeholder mismatch at "
                    f"{'.'.join(path_tuple)} — left as [TODO]",
                    file=sys.stderr,
                )
                stats["skipped"] += 1
                continue
            if not dry_run:
                _set_in(data, path_tuple, translated)
            stats["translated"] += 1

    if not dry_run and stats["translated"]:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="all", help="locale code or 'all'")
    parser.add_argument("--batch", type=int, default=20, help="strings per request")
    parser.add_argument("--limit", type=int, default=0, help="max strings/lang (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.lang == "all":
        langs = [c for c in LANG_NAMES if (LOCALES_DIR / c).is_dir()]
    else:
        langs = [args.lang]

    base, model, _key = _endpoint()
    print(f"Endpoint: {base}  model: {model}  (dry-run={args.dry_run})")
    grand = {"translated": 0, "skipped": 0, "todo": 0}
    for lang in langs:
        stats = translate_lang(lang, args.batch, args.limit, args.dry_run)
        print(
            f"  {stats['lang']:6} todo={stats['todo']:4} "
            f"translated={stats['translated']:4} skipped={stats['skipped']:4}"
        )
        for which in grand:
            grand[which] += stats[which]
    print(
        f"TOTAL todo={grand['todo']} translated={grand['translated']} "
        f"skipped={grand['skipped']}"
    )
    # Skips (placeholder mismatches / endpoint errors) are a soft failure:
    # the run still made progress, but flag non-zero so CI/automation sees it.
    return 1 if grand["skipped"] else 0


if __name__ == "__main__":
    sys.exit(main())
