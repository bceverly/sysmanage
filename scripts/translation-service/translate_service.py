#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
SysManage translation service — GPU/LLM-backed localization for the i18n pass.

A small, self-contained FastAPI service you run on the GPU "beast" box.  It
wraps a local instruction LLM (served by Ollama) behind a simple HTTP API: feed
it English source strings and it returns translations into the 13 non-English
locales SysManage supports.  The per-project backfill clients (docs / backend /
frontend / agent) call this over the LAN to fill in real translations instead of
``[TODO]`` placeholders.

Why an instruction LLM (not a dedicated MT model): UI/doc/log strings are full
of interpolation placeholders (``{{count}}``, ``%s``, ``%(name)s``, ``${VAR}``),
HTML/markup, markdown, file paths, CLI commands and brand names that MUST survive
translation verbatim.  A well-prompted LLM preserves those; classic MT models
mangle them.

Endpoints:
  GET  /health              — model + Ollama reachability
  GET  /languages           — the 13 supported target locales
  POST /translate           — one string  -> {lang: translation, ...}
  POST /translate/batch     — many strings -> aligned results (THE efficient path)

Run it:
  pip install -r requirements.txt
  # Ollama running + model pulled (see README.md), then:
  TRANSLATION_MODEL=qwen2.5:14b-instruct ./translate_service.py
  # or: uvicorn translate_service:app --host 0.0.0.0 --port 8765

Configuration (env vars):
  OLLAMA_URL          default http://localhost:11434
  TRANSLATION_MODEL   default: AUTO-SELECTED from detected VRAM (CPU model if no
                      GPU).  Set this to pin a specific Ollama tag and skip
                      auto-selection.
  SERVICE_HOST        default 0.0.0.0
  SERVICE_PORT        default 8765
  MAX_BATCH           default 40    (strings per LLM call; chunked above this)
  LANG_CONCURRENCY    default 3     (target languages translated in parallel)
  OLLAMA_TIMEOUT      default 600    (seconds per LLM call)
  NUM_CTX             default 8192  (Ollama context window)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import unicodedata
from collections import Counter
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
SERVICE_HOST = os.getenv("SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8765"))
MAX_BATCH = int(os.getenv("MAX_BATCH", "40"))
LANG_CONCURRENCY = int(os.getenv("LANG_CONCURRENCY", "3"))
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "600"))
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))
# Keep the (single, multilingual) model resident in VRAM between calls so a pass
# never pays an idle-unload reload.  Ollama's default is 5m; "30m" gives slack
# for slow client processing between batches, "-1" pins it forever.  There is no
# per-language model — switching target language is a prompt change on the same
# resident weights, so this one value covers all 13 languages.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")


# ---------------------------------------------------------------------------
# Turnkey model selection
# ---------------------------------------------------------------------------
# One multilingual model serves all 13 languages, so the model is a single
# choice sized to the hardware.  By default we DETECT total VRAM and pick the
# largest model that fits with headroom.  Set TRANSLATION_MODEL to pin a
# specific tag and skip all of this.

# WHY AYA AND NOT QWEN (changed 2026-08-14, measured, not assumed).
#
# This ladder used to select qwen2.5, and on a 16 GiB card that meant
# qwen2.5:14b-instruct.  That model BLEEDS ITS DOMINANT LANGUAGE: under a long
# or tag-dense string it drifts back to Chinese mid-sentence.  It had written
# 1,146 corrupted values across the four repos before anything caught it —
# Arabic containing Chinese, Hindi containing Cyrillic ("पлатफ़ोर्म"), Hindi
# containing katakana ("सेटअップ"), one Arabic value carrying the model's own
# commentary ("your answer seems to deviate from the task requirements") as if
# it were prose.  Every guard passed it, because they all asked "is the
# expected script present?" rather than "is an unexpected one present?".
#
# Benchmarked head to head on 20 known-bad strings across ar/hi/ko/zh_TW:
#     qwen2.5:14b-instruct   2 of 8 clean   (75% contaminated)
#     aya-expanse:8b        20 of 20 clean  (0% contaminated)
# and on the full 1,093-string docs re-translation aya was 95% filled with
# zero markup loss.  Aya Expanse is purpose-built multilingual (23 languages)
# and has no Chinese-dominant bias, which is the specific failure here.
#
# ~Q4 footprints: aya 8b≈6, aya 32b≈20 GiB; tiers leave room for KV-cache.
_MODEL_TIERS = [
    (22.0, "aya-expanse:32b"),
    (6.0, "aya-expanse:8b"),
    # Under 6 GiB aya:8b partially offloads to CPU — slow, but correct.  A
    # smaller qwen would be faster and would quietly corrupt the output again,
    # which is not a trade worth making for a job that runs overnight.
    (0.0, "aya-expanse:8b"),
]
# No GPU: still gives usable translations, just slowly, on CPU.
_CPU_MODEL = "aya-expanse:8b"


def _detect_vram_gib() -> Optional[float]:
    """Largest NVIDIA GPU's TOTAL VRAM in GiB via nvidia-smi, or None (no GPU)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    totals = []
    for line in out.splitlines():
        try:
            totals.append(int(line.strip()) / 1024)
        except ValueError:
            # Non-numeric nvidia-smi output line (header/blank) — skip it.
            continue
    return max(totals) if totals else None


def _auto_select_model(vram_gib: Optional[float]) -> str:
    if vram_gib is None:
        return _CPU_MODEL
    for floor, model in _MODEL_TIERS:
        if vram_gib >= floor:
            return model
    return _MODEL_TIERS[-1][1]


_VRAM_GIB = _detect_vram_gib()
_MODEL_ENV = os.getenv("TRANSLATION_MODEL")
TRANSLATION_MODEL = _MODEL_ENV or _auto_select_model(_VRAM_GIB)
if _MODEL_ENV:
    MODEL_SOURCE = "TRANSLATION_MODEL override"
elif _VRAM_GIB is not None:
    MODEL_SOURCE = f"auto-selected for {_VRAM_GIB:.1f} GiB VRAM"
else:
    MODEL_SOURCE = "auto-selected for CPU (no GPU detected)"

# The 13 non-English locales SysManage ships (matches assets/locales and the
# backend/agent gettext catalogs).  Keys are our locale codes; values are the
# human language names the LLM is prompted with.
LANGUAGES: Dict[str, str] = {
    "ar": "Arabic",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh_CN": "Simplified Chinese",
    "zh_TW": "Traditional Chinese",
}

# A string with no letters at all (pure placeholders / punctuation / numbers /
# code) is returned unchanged — never worth an LLM round-trip, and translating
# it risks corrupting a ``{{token}}`` or ``%s``.
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

SYSTEM_PROMPT = """You are a professional software-localization engine for the \
SysManage product. You translate UI labels, documentation, log messages and \
error messages from English into {language}.

ABSOLUTE RULES — follow every one:
1. Preserve, byte-for-byte and in place, anything that is not natural-language \
prose:
   - interpolation placeholders in ANY syntax: {{name}}, {name}, %s, %d, %(x)s, \
{0}, ${VAR}, $VAR, :name, <0>...</0>
   - HTML/XML tags and entities: <code>, <b>, </b>, &mdash;, &amp;, &gt;
   - markdown, URLs, file paths, environment variables, CLI commands and flags, \
and code snippets
2. Do NOT translate product, brand, project, protocol or technology names. Keep \
them exactly: SysManage, OpenBAO, PostgreSQL, SQLite, OpenTelemetry, Grafana, \
Graylog, Prometheus, Ubuntu, Debian, FreeBSD, OpenBSD, NetBSD, Windows, macOS, \
Linux, Docker, Kubernetes, WSL, LXD, KVM, bhyve, JWT, mTLS, TLS, SSH, RBAC, \
SAML, REST, API, CPU, GPU, RAM, UUID.
3. Keep leading/trailing whitespace, capitalization style, and trailing \
punctuation consistent with the source.
4. Translate the meaning naturally and idiomatically for a technical audience — \
do not translate word-for-word.
5. If a string is only a placeholder/code/symbol with no translatable words, \
return it unchanged.

OUTPUT: Return ONLY a JSON object of the exact form \
{"translations": ["...", "..."]} where "translations" is an array with EXACTLY \
the same number of elements as the input array, the i-th element being the \
{language} translation of the i-th input string, in the same order. No prose, \
no markdown fences, no extra keys."""

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TranslateRequest(BaseModel):
    text: str = Field(..., description="The English source string.")
    targets: Optional[List[str]] = Field(
        None,
        description="Subset of locale codes to translate into. Defaults to all 13.",
    )
    require_change: bool = Field(
        False,
        description=(
            "Treat output identical to the input as a FAILURE, not a result. "
            "Callers that already filter intentionally-English strings through "
            "their own allow-list know that anything they still send MUST "
            "change; setting this lets the service retry those against the "
            "model instead of returning the English and having it written."
        ),
    )


class BatchTranslateRequest(BaseModel):
    texts: List[str] = Field(..., description="English source strings.")
    targets: Optional[List[str]] = Field(
        None,
        description="Subset of locale codes to translate into. Defaults to all 13.",
    )
    require_change: bool = Field(
        False,
        description=(
            "Treat output identical to the input as a FAILURE, not a result. "
            "Callers that already filter intentionally-English strings through "
            "their own allow-list know that anything they still send MUST "
            "change; setting this lets the service retry those against the "
            "model instead of returning the English and having it written."
        ),
    )


# ---------------------------------------------------------------------------
# Core translation
# ---------------------------------------------------------------------------


def _resolve_targets(targets: Optional[List[str]]) -> List[str]:
    if not targets:
        return list(LANGUAGES.keys())
    unknown = [t for t in targets if t not in LANGUAGES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target locale(s): {unknown}. Supported: {list(LANGUAGES)}",
        )
    return targets


def _chunks(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# Tokens that MUST appear verbatim in a translation: interpolation placeholders,
# template vars, printf specifiers, HTML tags and entities.  Used to verify the
# model didn't drop/alter one (a 14b model occasionally drops e.g. {{count}} in a
# lower-resource language).  Ordered so the most specific form matches first.
# NB: the {{...}} form uses [^{}] rather than .*? so a match can't overlap
# braces — .*? there backtracks polynomially on adversarial input (ReDoS).
# Every quantifier below is UPPER-BOUNDED: this regex runs via ``findall`` over
# uncontrolled translation text, and an unbounded terminator-seeking branch
# (e.g. ``[^}]+\}`` or ``[a-zA-Z]+;``) with no terminator is O(n^2) across all
# start positions (CodeQL py/polynomial-redos).  Bounding the repeats caps the
# per-position work to a constant; the bounds are far larger than any real
# placeholder / tag / HTML entity, so extraction is unchanged in practice.
# How many CORRECTIVE retries a bad translation gets before the English source
# is kept.  Each one is told what the previous attempt got wrong; two is enough
# because the failure kind usually changes between them (fix the markup, expose
# an untranslated reply) and a third rarely converged in testing.
MAX_CORRECTIONS = 2

_PLACEHOLDER_RE = re.compile(
    r"\{\{[^{}]{0,200}\}\}"  # {{ name }}  (i18next / handlebars)
    r"|\$\{[^}]{1,200}\}"  # ${VAR}
    r"|\{[^{}]{0,200}\}"  # { name } { 0 }  (ICU / .NET / python)
    r"|%\d{1,9}\$[sdfgex]"  # %1$s
    r"|%\(\w{1,100}\)[sdfgexr]"  # %(name)s
    r"|%[sdfgexr%]"  # %s %d %%
    r"|\$[A-Za-z_]\w{0,100}"  # $VAR
    r"|</?[A-Za-z][^>]{0,1000}>"  # <tag ...>  </tag>  <br/>
    r"|&[a-zA-Z]{1,40};|&#\d{1,10};"  # &mdash;  &#8212;
)


def _placeholders_ok(src: str, translated: str) -> bool:
    """True iff ``translated`` carries EXACTLY the placeholders/tags/entities
    of ``src`` — none dropped and none invented.

    The check used to be one-directional ("did every source token survive?"),
    which let an INVENTED placeholder through: the model returned
    ``'{{days}} الدرة إون ال{{at}}'`` for ``'{{days}} day(s) ago'``, the
    required ``{{days}}`` was present, so the guard passed and a bogus
    ``{{at}}`` reached the locale file — surfacing hours later as a
    ``make i18n-placeholders`` failure. Counted as a multiset so a token
    duplicated in the translation is caught too (the same bug appeared in the
    .po catalogs as a doubled ``%s``, which raises TypeError at runtime).
    """
    return Counter(_PLACEHOLDER_RE.findall(src)) == Counter(
        _PLACEHOLDER_RE.findall(translated)
    )


# Locales whose output must be written in a specific Unicode script.  The model
# is prompted with the target language but sometimes answers in a DIFFERENT one
# — and nothing here noticed, so it was returned and written to the locale file.
# Real damage, found 2026-08-05: the Arabic locale held Chinese in 52 places in
# the frontend, 21 more in the backend catalogs and 363 in the docs; Hindi held
# Korean and Japanese. Every wrong language observed was one of our own 13
# targets, i.e. the model drifting between them rather than emitting noise.
_EXPECTED_SCRIPT = {
    "ar": ("ARABIC",),
    "hi": ("DEVANAGARI",),
    "ru": ("CYRILLIC",),
    "ja": ("CJK", "HIRAGANA", "KATAKANA"),
    "ko": ("HANGUL", "CJK"),
    "zh_CN": ("CJK",),
    "zh_TW": ("CJK",),
}
_SCRIPT_TAGS = (
    "ARABIC",
    "DEVANAGARI",
    "CYRILLIC",
    "HANGUL",
    "HIRAGANA",
    "KATAKANA",
    "CJK",
    "LATIN",
)


# Advertised on /health so a deploy is verifiable.  Add a name here whenever a
# new output guard lands, so `curl .../health` distinguishes builds.
# "untranslated" is opt-in per request (require_change) — advertised so a
# deploy is verifiable, same as the other two.
SERVICE_GUARDS = ("placeholders", "language", "untranslated")


def _scripts_used(text: str) -> set:
    """Unicode scripts present in ``text``, ignoring Latin.

    Latin is excluded because a correct translation legitimately carries
    product names, CLI snippets and acronyms in Latin script.
    """
    found = set()
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        for tag in _SCRIPT_TAGS:
            if name.startswith(tag) or tag in name.split()[0:2]:
                found.add(tag)
                break
    return found - {"LATIN"}


def _language_ok(lang_code: str, translated: str) -> bool:
    """True unless the answer contains a script this locale never uses.

    Rewritten 2026-08-14.  This used to ask "is ANY expected script present?"::

        return not used or bool(used & set(expected))

    which passes a MIXED answer — mostly-correct Arabic with Chinese spliced
    into the middle intersects {ARABIC} and sails through.  That is precisely
    what this model produces when it loses the thread on a long string, and 410
    such values had accumulated in sysmanage-docs (ar 275, hi 50, de 40, ru 16,
    es 13, fr 9, pt 4, nl 2, it 1) before anything noticed, including one
    carrying the model's own commentary ("your answer seems to deviate from the
    task requirements") as if it were prose.

    So the question is now the opposite one: is any script present that this
    locale never uses?  Latin is already excluded by _scripts_used, so product
    names and paths still pass.

    A locale with no expectation (the Latin-script targets) now means EXACTLY
    that — no non-Latin script at all.  Those locales were previously exempt
    from this guard entirely, which is how German picked up 40 Chinese values.
    Telling French from Spanish still needs real language ID and is still out
    of scope; this only catches a different alphabet, which is unambiguous.
    """
    expected = set(_EXPECTED_SCRIPT.get(lang_code) or ())
    used = _scripts_used(translated)
    return not (used - expected)


# Lone/unpaired UTF-16 surrogate code points (U+D800–U+DFFF).  The LLM
# occasionally emits one (e.g. a half-formed character or a broken \uDXXX JSON
# escape); ``json.loads`` accepts it into a Python str, but it CANNOT be UTF-8
# encoded, so FastAPI/pydantic crashes serializing the response
# (PydanticSerializationError: surrogates not allowed).  Strip them so the
# string is always valid UTF-8 — any resulting degradation is caught by the
# placeholder guard / English fallback downstream.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _strip_surrogates(text: str) -> str:
    return _SURROGATE_RE.sub("", text) if text else text


def _correction_note(reason: str, src: str, lang_code: str) -> str:
    """A specific instruction for the retry, naming what went wrong.

    Sampling runs at ``temperature: 0``, so re-sending the SAME prompt is
    deterministic — the retry reproduced the identical bad answer by
    construction and every failure burned a second GPU call for nothing.
    Changing the prompt is what makes the second attempt a real attempt.
    """
    language = LANGUAGES[lang_code]
    if reason == "markers":
        count = len(_PLACEHOLDER_RE.findall(src))
        return (
            "Your previous answer contained a ⟦n⟧ marker that was not in the "
            f"input. The input has exactly {count} marker(s), numbered ⟦0⟧ to "
            f"⟦{max(count - 1, 0)}⟧. Reproduce those and only those — do not "
            "renumber them and do not add new ones."
        )
    if reason == "placeholders":
        want = Counter(_PLACEHOLDER_RE.findall(src))
        tokens = ", ".join(
            f"{tok!r}" + (f" (x{n})" if n > 1 else "")
            for tok, n in sorted(want.items())
        )
        return (
            "Your previous answer did not reproduce the non-translatable tokens "
            "correctly. The translation MUST contain exactly these tokens, "
            f"byte-for-byte, no more and no fewer: {tokens}. Translate only the "
            "prose around them; copy every tag, entity and placeholder verbatim."
        )
    if reason == "language":
        scripts = " or ".join(_EXPECTED_SCRIPT.get(lang_code, ("the target script",)))
        return (
            f"Your previous answer was NOT in {language}. Answer in {language}, "
            f"written in the {scripts} script. Do not answer in any other language."
        )
    if reason == "untranslated":
        return (
            "Your previous answer was identical to the English input. The caller "
            "has already filtered out the strings that are meant to stay English, "
            f"so this one IS translatable — give the {language} translation."
        )
    return ""


# Markup masking.  The model is asked to reproduce every tag, entity and
# placeholder byte-for-byte, and on a long, tag-dense docs paragraph it reliably
# fails: it translates the text inside <code>, drops an </em>, or re-orders
# attributes, and the placeholder guard then rejects an otherwise good
# translation.  Masking replaces each token with a short opaque marker BEFORE
# the model sees it and restores the exact original afterwards, so tag fidelity
# stops depending on the model at all — it only has to carry a marker through,
# which it is far better at.
#
# The marker uses mathematical white square brackets: not present in any source
# string, not a word in any target language, and visually distinct enough that a
# model does not try to translate or "correct" it.
_MASK_RE = re.compile(r"⟦\s*(\d{1,3})\s*⟧")


def _mask_markup(text: str) -> Tuple[str, List[str]]:
    """``(masked_text, originals)`` — every placeholder/tag replaced by ⟦n⟧."""
    originals: List[str] = []

    def swap(match: re.Match) -> str:
        originals.append(match.group(0))
        return f"⟦{len(originals) - 1}⟧"

    return _PLACEHOLDER_RE.sub(swap, text), originals


def _unmask_markup(text: str, originals: List[str]) -> str:
    """Restore ⟦n⟧ markers to their exact original tokens.

    An out-of-range index is left as-is; it then fails the placeholder guard,
    which is the correct outcome — the model invented a marker.
    """

    def swap(match: re.Match) -> str:
        idx = int(match.group(1))
        return originals[idx] if 0 <= idx < len(originals) else match.group(0)

    return _MASK_RE.sub(swap, text)


# Sentence segmentation, the last resort before keeping English.
#
# Masking fixed markup fidelity for almost everything, but the longest docs
# paragraphs (370-960 chars, 6-10 tags) still failed: over that much text the
# model reworks clause order and a marker pair ends up dropped or misplaced, so
# the placeholder guard rejects the whole paragraph.  Translating one sentence
# at a time gives the model a short span with two or three markers instead of a
# page with ten, and the results are re-joined with the ORIGINAL separators so
# the reconstruction is exact.
#
# Splits only after . ! ? followed by whitespace and something that starts a new
# sentence (capital, a tag, or a marker).  "license.phone_home_url" and
# "3.11" have no space after the period, so they never split.
# The whitespace run is BOUNDED, not `\s+`.  Unbounded, this is a polynomial
# ReDoS on request-controlled text (CodeQL): for a long run of whitespace whose
# lookahead fails, the engine retries a shrinking `\s+` from every position
# inside the run — O(n^2) for a payload like ". " + " " * 100000.  Eight covers
# every real sentence separator (" ", "  ", "\n", "\n\n", CRLF); a longer run
# simply is not treated as a sentence boundary, which is harmless because the
# text is re-joined with the ORIGINAL separators either way.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])(\s{1,8})(?=[A-Z<⟦])")


# Abbreviations whose trailing period is NOT a sentence end.  Without this,
# "Use e.g. Docker." is cut into "Use e.g." + "Docker." and the model is asked
# to translate a two-word fragment with no subject — grammatical gender and
# verb form then come out wrong in the Romance and Slavic targets.
_ABBREV_END = re.compile(
    r"(?:^|[\s(])(?:e\.g|i\.e|etc|vs|cf|approx|incl|Dr|Mr|Mrs|Ms|St|Fig|No|Inc|Ltd)\.$"
)


def _segments(text: str) -> Tuple[List[str], List[str]]:
    """``(sentences, separators)`` such that re-joining reproduces ``text``."""
    parts = _SENTENCE_SPLIT.split(text)
    segments, separators = parts[0::2], parts[1::2]
    merged_segments: List[str] = []
    merged_separators: List[str] = []
    idx = 0
    while idx < len(segments):
        current = segments[idx]
        # Glue the next sentence back on while this "end" is an abbreviation.
        while idx < len(separators) and _ABBREV_END.search(current):
            current += separators[idx] + segments[idx + 1]
            idx += 1
        merged_segments.append(current)
        if idx < len(separators):
            merged_separators.append(separators[idx])
        idx += 1
    return merged_segments, merged_separators


def _rejoin(segments: List[str], separators: List[str]) -> str:
    """Inverse of :func:`_segments` — exact, separator-for-separator."""
    out: List[str] = []
    for idx, seg in enumerate(segments):
        out.append(seg)
        if idx < len(separators):
            out.append(separators[idx])
    return "".join(out)


async def _raw_chunk(
    client: httpx.AsyncClient,
    lang_code: str,
    sources: List[str],
    correction: Optional[str] = None,
) -> List[str]:
    """One Ollama call for a chunk -> length-aligned translations.

    Placeholders and markup are masked out before the call and restored after,
    so the model never has to reproduce a tag.  On any failure or length
    mismatch the items are retried one-at-a-time, and anything still failing
    falls back to the English source, so the result is always complete and
    aligned (never a crash mid-pass).  Placeholder integrity is enforced by
    ``_ollama_translate_chunk`` on top of this.
    """
    language = LANGUAGES[lang_code]
    masked_sources: List[str] = []
    masks: List[List[str]] = []
    for src in sources:
        masked, originals = _mask_markup(src)
        masked_sources.append(masked)
        masks.append(originals)
    payload = {
        "model": TRANSLATION_MODEL,
        "format": "json",
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.replace("{language}", language),
            },
            {
                "role": "user",
                "content": json.dumps(masked_sources, ensure_ascii=False),
            },
        ],
    }
    if any(masks):
        payload["messages"].insert(
            1,
            {
                "role": "system",
                "content": (
                    "Some inputs contain markers of the form ⟦0⟧, ⟦1⟧, ⟦2⟧ … "
                    "Each stands for a piece of markup or an interpolation "
                    "placeholder that has been removed. Copy every marker into "
                    "your translation EXACTLY as written, keeping the same "
                    "number of them, and place each one where the corresponding "
                    "content belongs in the target language. Never translate, "
                    "renumber, merge, drop or invent a marker."
                ),
            },
        )
    if correction:
        payload["messages"].insert(1, {"role": "system", "content": correction})
    try:
        # OLLAMA_URL is operator config (env/default localhost), NOT request
        # input — not attacker-controllable, so this is not SSRF.
        resp = await client.post(  # nosemgrep: tainted-fastapi-http-request-httpx
            f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        out = parsed["translations"] if isinstance(parsed, dict) else parsed
        if isinstance(out, list) and len(out) == len(sources):
            # Restore the masked markup, then strip lone surrogates the model may
            # emit — they'd be valid here but crash JSON serialization of the
            # HTTP response.
            return [
                _strip_surrogates(_unmask_markup(str(x), originals))
                for x, originals in zip(out, masks)
            ]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        # Transport/parse error or shape mismatch: fall through to the
        # one-at-a-time retry below rather than failing the whole chunk.
        pass

    # Length mismatch or error: retry one-at-a-time so a single bad string
    # can't poison the whole chunk.  If even that fails, keep the English.
    if len(sources) > 1:
        results: List[str] = []
        for s in sources:
            single = await _raw_chunk(client, lang_code, [s])
            results.append(single[0])
        return results
    return list(sources)  # give back the English source as a last resort


async def _ollama_translate_chunk(
    client: httpx.AsyncClient,
    lang_code: str,
    sources: List[str],
    require_change: bool = False,
) -> List[Tuple[str, str]]:
    """Translate a chunk AND guarantee placeholder + language integrity.

    A translation that mangled its placeholders, or came back in the wrong
    language entirely, is retried once on its own; if it is still bad the
    English source is kept.  Returning English is the right failure mode for
    both: a later pass can retry it, and the strict gate reports it — whereas
    shipping a placeholder-corrupted string breaks interpolation at runtime,
    and shipping Korean text to Arabic users is worse than shipping English.
    """

    def why_bad(src: str, txt: str) -> Optional[str]:
        if _MASK_RE.search(txt):
            # A mask marker survived restoration, so the model invented one
            # (an index we never issued) or mangled its digits.  Unmasking
            # leaves those literal, and _placeholders_ok would NOT catch it —
            # ⟦9⟧ is not a placeholder — so a stray marker would land in the
            # locale file and render to users verbatim.
            return "markers"
        if not _placeholders_ok(src, txt):
            return "placeholders"
        if not _language_ok(lang_code, txt):
            return "language"
        if require_change and txt.strip() == src.strip():
            # The caller filters its intentionally-English strings out before
            # sending, so anything that arrives here MUST change.  Without this
            # the language guard passes an all-Latin reply (it cannot tell a
            # product name from the model giving up), the client writes the
            # English, and the string is silently never translated.
            return "untranslated"
        return None

    out = await _raw_chunk(client, lang_code, sources)
    repaired: List[Tuple[str, str]] = []
    for src, txt in zip(sources, out):
        reason = why_bad(src, txt)
        if reason is None:
            repaired.append((txt, "ok"))
            continue
        # Retry this one string alone, HERE on the GPU box.  Doing it here
        # rather than letting the caller re-POST is the whole point: the
        # client cannot tell "the model legitimately kept this as-is" from
        # "we gave up and returned the English", so it used to re-send over
        # the network and guess — which looped forever on strings whose
        # correct answer IS the English.
        #
        # The retry carries a CORRECTION naming the specific failure.  Sampling
        # is temperature 0, so an identical prompt returns an identical answer:
        # the old blind retry could not possibly succeed where the first call
        # failed, which is why markup-heavy docs strings sat at
        # "fallback:placeholders" run after run.
        # Up to MAX_CORRECTIONS attempts, each told what the LAST one got wrong.
        # A second pass is worth it because the failures change kind: fixing the
        # markup often exposes an untranslated reply, and vice versa.
        cand = src
        for _ in range(MAX_CORRECTIONS):
            note = _correction_note(reason, src, lang_code)
            retry = await _raw_chunk(client, lang_code, [src], correction=note)
            cand = retry[0] if retry else src
            reason = why_bad(src, cand)
            if reason is None:
                break
        if reason is None:
            repaired.append((cand, "ok"))
            continue

        # Last resort: translate sentence by sentence and re-join.  A long
        # paragraph the model cannot carry markers across in one piece is
        # usually fine in three-sentence bites.
        segments, separators = _segments(src)
        if len(segments) > 1:
            translated = await _raw_chunk(client, lang_code, segments)
            stitched = _rejoin(translated, separators)
            # _raw_chunk falls back to English PER SEGMENT, so a paragraph can
            # come back with one untranslated sentence embedded in it.  The
            # stitched result would then differ from the English source, so
            # neither the require_change check here nor the strict gate
            # downstream would notice — a silent half-translation.  Demand that
            # every segment carrying letters actually moved.
            stalled = [
                seg
                for seg, out in zip(segments, translated)
                if _HAS_LETTER.search(seg) and out.strip() == seg.strip()
            ]
            if not stalled and why_bad(src, stitched) is None:
                # Plain "ok", NOT "ok:segmented": every client tests
                # ``status == "ok"`` exactly, so a decorated success value would
                # be read as a failure and this translation thrown away.
                repaired.append((stitched, "ok"))
                continue

        repaired.append((src, f"fallback:{reason}"))
    return repaired


async def _translate_one_language(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lang_code: str,
    translatable: List[str],
    require_change: bool = False,
) -> List[Tuple[str, str]]:
    async with sem:
        out: List[Tuple[str, str]] = []
        for chunk in _chunks(translatable, MAX_BATCH):
            out.extend(
                await _ollama_translate_chunk(client, lang_code, chunk, require_change)
            )
        return out


async def _translate(
    texts: List[str], targets: List[str], require_change: bool = False
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Translate ``texts`` into every code in ``targets``.

    Returns ``(translations, statuses)`` — one dict per input string each.
    ``statuses[i][lang]`` is ``"ok"`` or ``"fallback:<reason>"``, so the client
    never has to infer failure from "the output equals the input".
    Pure-placeholder/empty strings are passed through unchanged for every
    language without hitting the model.
    """
    # Split into the indices that actually need translating vs. pass-throughs.
    needs_idx = [i for i, t in enumerate(texts) if _HAS_LETTER.search(t)]
    translatable = [texts[i] for i in needs_idx]

    per_lang: Dict[str, List[str]] = {}
    if translatable:
        sem = asyncio.Semaphore(LANG_CONCURRENCY)
        async with httpx.AsyncClient() as client:
            tasks = {
                code: _translate_one_language(
                    client, sem, code, translatable, require_change
                )
                for code in targets
            }
            done = await asyncio.gather(*tasks.values())
        per_lang = dict(zip(tasks.keys(), done))

    # Reassemble aligned to the original input order, restoring pass-throughs.
    results: List[Dict[str, str]] = []
    statuses: List[Dict[str, str]] = []
    back = {orig_i: j for j, orig_i in enumerate(needs_idx)}
    for i, src in enumerate(texts):
        row: Dict[str, str] = {}
        srow: Dict[str, str] = {}
        for code in targets:
            if i in back:
                row[code], srow[code] = per_lang[code][back[i]]
            else:
                # Pure placeholder/empty: never sent to the model, and the
                # source IS the correct output — report it as ok so the client
                # writes it instead of treating "unchanged" as a failure.
                row[code], srow[code] = src, "ok"
        results.append(row)
        statuses.append(srow)
    return results, statuses


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _gpu_info() -> List[str]:
    """Best-effort GPU/VRAM lines via nvidia-smi (no torch/CUDA dependency)."""
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ["GPU        : none detected via nvidia-smi (CPU or non-NVIDIA)"]
    if proc.returncode != 0:
        # nvidia-smi exists but failed. The common cause on a box that DOES have
        # a GPU is a driver/library version mismatch after an unrebooted driver
        # update — name it explicitly with the fix, since the generic "no GPU"
        # line sent the operator on a hunt last time.
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err[0] if err else f"nvidia-smi exited {proc.returncode}"
        out_lines = [f"GPU        : nvidia-smi FAILED — {detail}"]
        low = detail.lower()
        if "mismatch" in low or "nvml" in low or "failed to initialize" in low:
            out_lines.append(
                "             -> NVIDIA driver/library version mismatch: REBOOT "
                "this box (or reload the nvidia kernel modules) to fix"
            )
        return out_lines
    out = proc.stdout.strip()
    lines: List[str] = []
    for row in out.splitlines():
        parts = [c.strip() for c in row.split(",")]
        if len(parts) != 4:
            continue
        idx, name, total_mib, free_mib = parts
        try:
            total_gib = int(total_mib) / 1024
            free_gib = int(free_mib) / 1024
            lines.append(
                f"GPU {idx}      : {name} — {total_gib:.1f} GiB total, "
                f"{free_gib:.1f} GiB free"
            )
        except ValueError:
            lines.append(f"GPU {idx}      : {name} — {total_mib} MiB total")
    return lines or ["GPU        : nvidia-smi reported no devices"]


def _remediation_lines() -> List[str]:
    """Operator hint lines when we're on the CPU fallback model (no GPU seen).

    The CPU-tier model translates poorly enough that it often echoes the source
    (which silently fails the downstream ``translate-check`` gate), so surface
    the exact recovery commands right in the service's own output instead of
    making the operator reverse-engineer it from a failed ``make lint``.
    """
    largest = _MODEL_TIERS[2][1]  # qwen2.5:14b-instruct — the usual GPU pick
    return [
        "no GPU detected -> using the CPU model, which may ECHO the source",
        "  to recover if this box HAS a GPU:",
        "    1. nvidia-smi                     # confirm the GPU is visible",
        "    2. ollama ps                      # is a model stuck loaded on CPU?",
        f"    3. ollama stop {TRANSLATION_MODEL}   # unload it "
        "(or: sudo systemctl restart ollama)",
        "    4. restart this service           # re-detects VRAM, picks the GPU model",
        f"  or force a specific pulled model:  TRANSLATION_MODEL={largest} "
        "python3 ./translate_service.py",
    ]


def _print_startup_banner() -> None:
    print("=" * 64, flush=True)
    print("SysManage translation service", flush=True)
    print(f"  model      : {TRANSLATION_MODEL}  [{MODEL_SOURCE}]", flush=True)
    print(f"  ollama     : {OLLAMA_URL}  (keep_alive={OLLAMA_KEEP_ALIVE})", flush=True)
    print(f"  listening  : {SERVICE_HOST}:{SERVICE_PORT}", flush=True)
    for line in _gpu_info():
        print(f"  {line}", flush=True)
    if _VRAM_GIB is None and not _MODEL_ENV:
        for line in _remediation_lines():
            print(f"  {line}", flush=True)
    print("=" * 64, flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Printed on startup whether launched via __main__ or `uvicorn translate_service:app`.
    _print_startup_banner()
    # Turnkey nudge: since the model is auto-chosen, tell the operator if it
    # still needs pulling (Ollama does not auto-pull on first request).
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
        base = TRANSLATION_MODEL.split(":")[0]
        if any(n == TRANSLATION_MODEL or n.split(":")[0] == base for n in names):
            print(f"  ollama     : model '{TRANSLATION_MODEL}' present ✓", flush=True)
        else:
            print(
                f"  ollama     : '{TRANSLATION_MODEL}' NOT pulled — run:  "
                f"ollama pull {TRANSLATION_MODEL}",
                flush=True,
            )
    except httpx.HTTPError:
        print(
            f"  ollama     : could not reach {OLLAMA_URL} to verify the model",
            flush=True,
        )
    print("=" * 64, flush=True)
    yield


app = FastAPI(
    title="SysManage Translation Service",
    description="LLM-backed English->13-locale translation for the i18n pass.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/languages")
async def languages() -> dict:
    return {"languages": LANGUAGES, "count": len(LANGUAGES)}


@app.get("/health")
async def health() -> dict:
    ollama_ok = False
    models: List[str] = []
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            ollama_ok = True
    except httpx.HTTPError:
        # Ollama unreachable for the tags probe — report it as not-ready in the
        # health payload rather than raising.
        pass
    model_pulled = any(
        m == TRANSLATION_MODEL or m.split(":")[0] == TRANSLATION_MODEL.split(":")[0]
        for m in models
    )
    return {
        "status": "ok" if (ollama_ok and model_pulled) else "degraded",
        "ollama_url": OLLAMA_URL,
        "ollama_reachable": ollama_ok,
        "model": TRANSLATION_MODEL,
        "model_source": MODEL_SOURCE,
        "model_pulled": model_pulled,
        "available_models": models,
        "target_languages": list(LANGUAGES.keys()),
        # Which output guards this build enforces.  Deployment is a manual scp
        # to the GPU box, so without this there is no way to tell a restarted
        # service from one still running the previous file — and the guards are
        # invisible when working (they only ever suppress bad output).
        "guards": sorted(SERVICE_GUARDS),
    }


@app.post("/translate")
async def translate(req: TranslateRequest) -> dict:
    targets = _resolve_targets(req.targets)
    rows, statuses = await _translate([req.text], targets, req.require_change)
    return {"source": req.text, "translations": rows[0], "status": statuses[0]}


@app.post("/translate/batch")
async def translate_batch(req: BatchTranslateRequest) -> dict:
    if not req.texts:
        return {"count": 0, "targets": _resolve_targets(req.targets), "results": []}
    targets = _resolve_targets(req.targets)
    rows, statuses = await _translate(req.texts, targets, req.require_change)
    return {
        "count": len(req.texts),
        "targets": targets,
        # ``status`` is per-language, alongside ``translations``: "ok" or
        # "fallback:<reason>".  Clients MUST branch on it rather than compare
        # the output to the input — comparing is what made strings whose
        # correct translation IS the English retry forever.
        "results": [
            {"source": src, "translations": row, "status": st}
            for src, row, st in zip(req.texts, rows, statuses)
        ],
    }


def main() -> None:
    import uvicorn

    # The model + GPU/VRAM banner is printed by the lifespan handler, so it
    # shows whether launched here or via `uvicorn translate_service:app`.
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT, log_level="info")


if __name__ == "__main__":
    main()
