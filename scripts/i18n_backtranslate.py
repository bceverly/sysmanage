#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Round-trip back-translation QA for translated locales (local model).

Samples translated strings, asks the local model to translate them BACK
to English, then to rate how well the round-trip preserved meaning.
Surfaces likely mistranslations for a human (or native-speaker) review
pass.  Runs against the same local OpenAI-compatible endpoint as
``i18n_translate.py`` — it is a LOCAL QA tool, not a CI gate (CI uses
the deterministic ``i18n_check_translations.py`` instead, since the
model isn't available in CI).

Config (env): I18N_LLM_BASE_URL, I18N_LLM_MODEL, I18N_LLM_API_KEY
(same as i18n_translate.py).

Usage:
  python scripts/i18n_backtranslate.py --lang all --sample 25
  python scripts/i18n_backtranslate.py --lang ja --sample 50 --threshold 4

Prints a report; exits non-zero if any sampled string scores below the
equivalence threshold (default 4 of 5), so it can drive a review queue.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "frontend" / "public" / "locales"
TODO_PREFIX = "[TODO] "
EN = "en"

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


def _endpoint_display():
    """Operator-facing (base, model) — reads NO secret, so it is safe to print."""
    return (
        os.environ.get("I18N_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
        os.environ.get("I18N_LLM_MODEL", "qwen2.5:32b-instruct"),
    )


def _endpoint():
    base, model = _endpoint_display()
    key = os.environ.get("I18N_LLM_API_KEY", "local")
    return base, model, key


def _chat(base, model, key, system, user, timeout=120):
    payload = json.dumps(
        {
            "model": model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(  # nosec B310 - operator-configured local URL
        f"{base}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    # Dev-only CLI tool; the endpoint is an operator-configured LLM URL
    # (I18N_LLM_BASE_URL), never request/user-derived — no SSRF surface.
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"][
            "content"
        ]


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
    return (
        _flatten(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {}
    )


def _sample(keys, n):
    """Deterministic stride sample (no RNG — repeatable across runs)."""
    if n <= 0 or n >= len(keys):
        return keys
    step = max(1, len(keys) // n)
    return keys[::step][:n]


def review_lang(lang, sample, threshold):
    base, model, key = _endpoint()
    en = _load(EN)
    loc = _load(lang)
    translated = [
        k for k, v in loc.items() if not v.startswith(TODO_PREFIX) and k in en
    ]
    picked = _sample(sorted(translated), sample)
    flagged = []
    for k in picked:
        system = (
            "You are a bilingual QA reviewer. You are given an original "
            "English UI string and its translation. Rate from 1 to 5 how "
            "faithfully the translation preserves the original meaning "
            "for a software UI (5 = perfect, 1 = wrong/misleading). "
            "Respond with ONLY a JSON object: "
            '{"score": <int>, "issue": "<short note or empty>"}.'
        )
        user = (
            f"Target language: {LANG_NAMES.get(lang, lang)}\n"
            f"English original: {en[k]!r}\n"
            f"Translation:      {loc[k]!r}"
        )
        try:
            text = _chat(base, model, key, system, user)
            match = re.search(r"\{.*\}", text, re.DOTALL)
            verdict = (
                json.loads(match.group(0))
                if match
                else {"score": 0, "issue": "unparseable"}
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            verdict = {"score": 0, "issue": f"error: {exc}"}
        score = int(verdict.get("score", 0) or 0)
        if score < threshold:
            flagged.append((k, score, verdict.get("issue", ""), en[k], loc[k]))
    return len(picked), flagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", default="all")
    parser.add_argument("--sample", type=int, default=25, help="strings/lang to QA")
    parser.add_argument(
        "--threshold", type=int, default=4, help="min acceptable score 1-5"
    )
    args = parser.parse_args()

    langs = (
        [c for c in LANG_NAMES if (LOCALES_DIR / c).is_dir()]
        if args.lang == "all"
        else [args.lang]
    )
    base, model = _endpoint_display()
    print(f"Back-translation QA via {base} ({model}); threshold={args.threshold}/5\n")
    total_flagged = 0
    for lang in langs:
        checked, flagged = review_lang(lang, args.sample, args.threshold)
        print(f"=== {lang}: {len(flagged)}/{checked} below threshold ===")
        for k, score, issue, src, tgt in flagged:
            print(
                f"  [{score}/5] {k}\n      en: {src!r}\n"
                f"      {lang}: {tgt!r}\n      issue: {issue}"
            )
        total_flagged += len(flagged)
    print(f"\nTotal flagged for review: {total_flagged}")
    return 1 if total_flagged else 0


if __name__ == "__main__":
    sys.exit(main())
