#!/usr/bin/env python3
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
  TRANSLATION_MODEL   default qwen2.5:14b-instruct
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
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "qwen2.5:14b-instruct")
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
{{"translations": ["...", "..."]}} where "translations" is an array with EXACTLY \
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


class BatchTranslateRequest(BaseModel):
    texts: List[str] = Field(..., description="English source strings.")
    targets: Optional[List[str]] = Field(
        None,
        description="Subset of locale codes to translate into. Defaults to all 13.",
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


async def _ollama_translate_chunk(
    client: httpx.AsyncClient, lang_code: str, sources: List[str]
) -> List[str]:
    """Translate one chunk of strings into one language via Ollama.

    Returns a list aligned with ``sources``.  On any failure or length
    mismatch the un-translatable items fall back to the English source so the
    caller always gets a complete, aligned result (never a crash mid-pass).
    """
    language = LANGUAGES[lang_code]
    payload = {
        "model": TRANSLATION_MODEL,
        "format": "json",
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
            {"role": "user", "content": json.dumps(sources, ensure_ascii=False)},
        ],
    }
    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        parsed = json.loads(content)
        out = parsed["translations"] if isinstance(parsed, dict) else parsed
        if isinstance(out, list) and len(out) == len(sources):
            return [str(x) for x in out]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        pass

    # Length mismatch or error: retry one-at-a-time so a single bad string
    # can't poison the whole chunk.  If even that fails, keep the English.
    if len(sources) > 1:
        results: List[str] = []
        for s in sources:
            single = await _ollama_translate_chunk(client, lang_code, [s])
            results.append(single[0])
        return results
    return list(sources)  # give back the English source as a last resort


async def _translate_one_language(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lang_code: str,
    translatable: List[str],
) -> List[str]:
    async with sem:
        out: List[str] = []
        for chunk in _chunks(translatable, MAX_BATCH):
            out.extend(await _ollama_translate_chunk(client, lang_code, chunk))
        return out


async def _translate(texts: List[str], targets: List[str]) -> List[Dict[str, str]]:
    """Translate ``texts`` into every code in ``targets``.

    Returns one dict per input string: ``{lang_code: translation, ...}``.
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
                code: _translate_one_language(client, sem, code, translatable)
                for code in targets
            }
            done = await asyncio.gather(*tasks.values())
        per_lang = dict(zip(tasks.keys(), done))

    # Reassemble aligned to the original input order, restoring pass-throughs.
    results: List[Dict[str, str]] = []
    back = {orig_i: j for j, orig_i in enumerate(needs_idx)}
    for i, src in enumerate(texts):
        row: Dict[str, str] = {}
        for code in targets:
            if i in back:
                row[code] = per_lang[code][back[i]]
            else:
                row[code] = src  # pure placeholder/empty: unchanged
        results.append(row)
    return results


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _gpu_info() -> List[str]:
    """Best-effort GPU/VRAM lines via nvidia-smi (no torch/CUDA dependency)."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return ["GPU        : none detected via nvidia-smi (CPU or non-NVIDIA)"]
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


def _print_startup_banner() -> None:
    print("=" * 64, flush=True)
    print("SysManage translation service", flush=True)
    print(f"  model      : {TRANSLATION_MODEL}", flush=True)
    print(f"  ollama     : {OLLAMA_URL}  (keep_alive={OLLAMA_KEEP_ALIVE})", flush=True)
    print(f"  listening  : {SERVICE_HOST}:{SERVICE_PORT}", flush=True)
    for line in _gpu_info():
        print(f"  {line}", flush=True)
    print("=" * 64, flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Printed on startup whether launched via __main__ or `uvicorn translate_service:app`.
    _print_startup_banner()
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
        "model_pulled": model_pulled,
        "available_models": models,
        "target_languages": list(LANGUAGES.keys()),
    }


@app.post("/translate")
async def translate(req: TranslateRequest) -> dict:
    targets = _resolve_targets(req.targets)
    rows = await _translate([req.text], targets)
    return {"source": req.text, "translations": rows[0]}


@app.post("/translate/batch")
async def translate_batch(req: BatchTranslateRequest) -> dict:
    if not req.texts:
        return {"count": 0, "targets": _resolve_targets(req.targets), "results": []}
    targets = _resolve_targets(req.targets)
    rows = await _translate(req.texts, targets)
    return {
        "count": len(req.texts),
        "targets": targets,
        "results": [
            {"source": src, "translations": row}
            for src, row in zip(req.texts, rows)
        ],
    }


def main() -> None:
    import uvicorn

    # The model + GPU/VRAM banner is printed by the lifespan handler, so it
    # shows whether launched here or via `uvicorn translate_service:app`.
    uvicorn.run(app, host=SERVICE_HOST, port=SERVICE_PORT, log_level="info")


if __name__ == "__main__":
    main()
