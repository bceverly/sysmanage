#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
"""``POST /verify/batch``: does each translation say what its English says?

The model half of ``scripts/i18n_verify.py``.  The client sends one locale's
``(source, translation)`` pairs; each comes back ``ok`` or with a reason.  A
pair passes when:

  1. the deterministic checks pass (``scripts/i18n_quality.py``, the same code
     the client and CI run, so the service never vouches for what CI rejects);
  2. a multilingual embedding places the translation next to its source:
     cosine >= PASS_AT passes, < FAIL_BELOW fails; and
  3. anything in between goes to a single-item judge, asked one question.

Why this shape, measured on beast (RTX 4060 Ti, 16 GiB) on 2026-10-08:

  * The judge ALONE is not usable.  Given eight pairs at once, aya-expanse:8b
    scored a wrong-key value ("Example Config" against a sentence about
    authenticator fallback) 5 of 5, and returned the wrong number of verdicts
    for whole batches.  One pair per call fixed both.
  * The judge cannot see mixed language: it passed every one of 25 half-English
    values and whole English paragraphs.  Language is therefore deterministic
    (English function words, i18n_quality.py), never asked of the model.
  * bge-m3 separates a translation from some OTHER key's text: 390 swapped
    pairs never exceeded 0.62, and 95% of real pairs scored above 0.66.  It is
    unreliable on one- and two-word strings ("Overview"/"Panoramica" scored
    0.41), which is why the middle band goes to the judge rather than failing.
  * PASS_AT is 0.65, not the 0.75 first shipped.  At 0.75 a quarter of all
    values (every short heading: "Log Locations", "Exporter Configuration")
    went to the judge one at a time, and the 266k-value docs pass estimated
    weeks.  0.65 is still above every swapped pair measured, and 95% of real
    pairs clear it, so the judge sees ~5%.
  * The judge prompt is EXACTLY the calibrated one.  A clause added after
    calibration ("each term is used in its systems-administration sense")
    made it reject 831 of the first 832 docs values, including correct
    Arabic headings it described as accurate in its own reason.  Re-run the
    calibration before changing a word of it.
  * On that middle band the judge rejected 24 of 25 swapped values and nine
    real ones -- every one genuinely broken (Hindi "Quick Navigation" rendered
    as gibberish, "fleet compliance report" as "network firewall compliance
    report") -- and passed all 25 good controls.
"""

from __future__ import annotations

import json
import math
import os
from typing import Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    import i18n_quality  # scripts/, put on sys.path by translate_service
except ImportError:  # pragma: no cover - deployment accident
    i18n_quality = None

EMBED_MODEL = os.getenv("VERIFY_EMBED_MODEL", "bge-m3")
PASS_AT = float(os.getenv("VERIFY_PASS_AT", "0.65"))
FAIL_BELOW = float(os.getenv("VERIFY_FAIL_BELOW", "0.40"))
JUDGE_MAX_TOKENS = 96
# Bump when a threshold, model or prompt changes, so a ledger can be traced to
# the verifier that wrote it (GET /health reports it).
VERIFIER_VERSION = f"2:{EMBED_MODEL}:{PASS_AT}:{FAIL_BELOW}"

JUDGE_PROMPT = """You check translations for a systems-administration product. You are given an English SOURCE and a {language} TRANSLATION.

Answer "yes" only if ALL of these hold:
- the TRANSLATION says what the SOURCE says (same meaning, nothing important missing or added; small wording differences are fine);
- it is not a translation of some other sentence.

Otherwise answer "no". Reply with JSON only: {{"answer": "yes" or "no", "reason": "<at most 12 words, in English>"}}"""


class VerifyItem(BaseModel):
    source: str
    value: str


class VerifyRequest(BaseModel):
    lang: str = Field(..., description="Locale code, e.g. 'fr' or 'zh_TW'.")
    items: List[VerifyItem]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


def make_router(
    ollama_url: str,
    judge_model: str,
    languages: Dict[str, str],
    mask: Callable[[str], Tuple[str, List[str]]],
    timeout: float,
    keep_alive: str,
) -> APIRouter:
    """The verify routes, bound to the service's own Ollama configuration."""
    router = APIRouter()

    async def embed(client: httpx.AsyncClient, texts: List[str]) -> List[List[float]]:
        # ollama_url is operator config, not request input.
        resp = await client.post(  # nosemgrep: tainted-fastapi-http-request-httpx
            f"{ollama_url}/api/embed",
            json={"model": EMBED_MODEL, "input": texts, "keep_alive": keep_alive},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def judge(
        client: httpx.AsyncClient, lang: str, source: str, value: str
    ) -> Tuple[bool, str]:
        payload = {
            "model": judge_model,
            "format": "json",
            "stream": False,
            "keep_alive": keep_alive,
            # A verdict is one short JSON line.  Uncapped, the model sometimes
            # never closes it: on beast it once generated 4,000+ tokens of
            # padding for one pair and held the whole run for minutes.
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_predict": JUDGE_MAX_TOKENS,
            },
            "messages": [
                {
                    "role": "system",
                    "content": JUDGE_PROMPT.format(language=languages[lang]),
                },
                {
                    "role": "user",
                    "content": f"SOURCE:\n{source}\n\nTRANSLATION:\n{value}",
                },
            ],
        }
        resp = await client.post(  # nosemgrep: tainted-fastapi-http-request-httpx
            f"{ollama_url}/api/chat", json=payload, timeout=timeout
        )
        resp.raise_for_status()
        try:
            verdict = json.loads(resp.json()["message"]["content"])
        except ValueError:
            # Truncated at JUDGE_MAX_TOKENS or not JSON at all: no verdict is
            # not a pass.  The pair is rejected and goes back for translation.
            return False, "the judge gave no readable verdict"
        if not isinstance(verdict, dict):
            return False, "the judge gave no readable verdict"
        answer = str(verdict.get("answer", "")).strip().lower()
        return answer == "yes", str(verdict.get("reason", "")).strip()

    @router.post("/verify/batch")
    async def verify_batch(req: VerifyRequest) -> dict:
        if req.lang not in languages:
            raise HTTPException(status_code=400, detail=f"Unknown locale {req.lang!r}")
        results: List[Optional[dict]] = [None] * len(req.items)
        to_embed: List[int] = []
        for i, item in enumerate(req.items):
            why = (
                i18n_quality.problem(req.lang, item.source, item.value)
                if i18n_quality
                else None
            )
            if why:
                results[i] = {"ok": False, "reason": why}
            else:
                to_embed.append(i)
        async with httpx.AsyncClient() as client:
            if to_embed:
                # Masked, so a tag-dense string is compared on its prose rather
                # than on the markup both sides share.
                sources = [mask(req.items[i].source)[0] for i in to_embed]
                values = [mask(req.items[i].value)[0] for i in to_embed]
                vectors = await embed(client, sources + values)
                half = len(to_embed)
                for n, i in enumerate(to_embed):
                    cos = round(_cosine(vectors[n], vectors[half + n]), 3)
                    if cos >= PASS_AT:
                        results[i] = {"ok": True, "cos": cos}
                    elif cos < FAIL_BELOW:
                        results[i] = {
                            "ok": False,
                            "cos": cos,
                            "reason": f"meaning: similarity {cos} to the source",
                        }
                    else:
                        ok, reason = await judge(
                            client, req.lang, req.items[i].source, req.items[i].value
                        )
                        results[i] = {
                            "ok": ok,
                            "cos": cos,
                            "judge": True,
                            "reason": (
                                "" if ok else f"meaning: {reason or 'judge said no'}"
                            ),
                        }
        return {"verifier": VERIFIER_VERSION, "results": results}

    return router
