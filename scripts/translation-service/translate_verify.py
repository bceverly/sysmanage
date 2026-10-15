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
  * The glossary (2026-10-14, scripts/i18n_judge_calibrate.py, judge alone):
    sent as a SECOND system message -- the prompt above is untouched -- it
    took the human-confirmed false alarms from 2/83 to 19/83 (sysmanage) and
    27/88 to 44/88 (docs; zh_TW 主機群 "fleet", "Dispatch" in seven
    languages), left good short / long values and swapped values as they
    were (one more swap rejected), and its one new rejection of a "good"
    value was a real defect (a French value missing half its sentence).
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
try:
    import i18n_glossary  # scripts/, the translator's own glossary
except ImportError:  # pragma: no cover - deployment accident
    i18n_glossary = None

EMBED_MODEL = os.getenv("VERIFY_EMBED_MODEL", "bge-m3")
PASS_AT = float(os.getenv("VERIFY_PASS_AT", "0.65"))
FAIL_BELOW = float(os.getenv("VERIFY_FAIL_BELOW", "0.40"))
JUDGE_MAX_TOKENS = 96
# The judge is told the product's own terms (23.4): without them it rejected
# the glossary's canonical zh_TW 主機群 for "fleet" as "a collection of
# vehicles".  Given as a SEPARATE system message, so JUDGE_PROMPT stays the
# calibrated text; scripts/i18n_judge_calibrate.py measures both ways.
JUDGE_GLOSSARY = os.getenv("VERIFY_JUDGE_GLOSSARY", "1") not in ("0", "false", "no")
# Bump when a threshold, model or prompt changes, so a ledger can be traced to
# the verifier that wrote it (GET /health reports it).
VERIFIER_VERSION = f"2:{EMBED_MODEL}:{PASS_AT}:{FAIL_BELOW}" + (
    ":gloss" if JUDGE_GLOSSARY else ""
)

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
    # Calibration only (scripts/i18n_judge_calibrate.py): every pair goes to
    # the judge, skipping the embedding bands, with or without the glossary.
    judge_only: bool = False
    glossary: Optional[bool] = None


def judge_terms(source: str, lang: str, language: str) -> str:
    """The judge's view of the glossary: what this source's product terms
    mean and how the product renders them -- framed as CORRECT renderings to
    accept, not (as the translator's version is) as instructions."""
    if i18n_glossary is None:
        return ""
    lines = []
    for term, gloss in i18n_glossary.relevant([source]):
        spec = i18n_glossary.TERMS.get(term, {})
        canonical = spec.get("canonical", {}).get(lang) if spec else None
        line = f"  - {term}: {gloss}"
        if canonical:
            line += f" (this product's {language} term: \u201c{canonical}\u201d)"
        lines.append(line)
    if not lines:
        return ""
    return (
        "DOMAIN TERMS. These words in the SOURCE are this product's own "
        "technical terms, with the meaning given; a TRANSLATION that renders "
        "them this way is correct, whatever the everyday sense of the word:\n"
        + "\n".join(lines)
    )


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


# How much better an answer must match ANOTHER item's source than its own before
# the batch counts as shifted.  Cross-lingual bge-m3 scores for a correct
# translation sit far above unrelated pairs, so a small margin only trips on a
# real shift, not on two similar short labels.
ALIGN_MARGIN = float(os.getenv("ALIGN_MARGIN", "0.05"))


async def aligned(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: httpx.AsyncClient,
    ollama_url: str,
    keep_alive: str,
    timeout: float,
    sources: List[str],
    answers: List[str],
) -> bool:
    """False when a batch's answers are evidently attached to the wrong items.

    The length check below cannot see this: the model sometimes returns the
    right NUMBER of answers in the wrong ORDER (or merges one item and splits
    another), and every value is then written under a neighbor's key.  Measured
    2026-10-11 on the docs: French page titles holding the "Export CSV" sentence.
    Each answer must match its own source at least as well as any other source.
    The embedding model is the verifier's (already resident); if it cannot be
    reached the batch is accepted -- this is a guard, never a reason to stop
    translating.
    """
    if len(sources) < 2:
        return True
    try:
        # nosemgrep: python.fastapi.net.tainted-fastapi-http-request-httpx.tainted-fastapi-http-request-httpx
        resp = await client.post(
            f"{ollama_url}/api/embed",
            json={
                "model": EMBED_MODEL,
                "input": list(sources) + list(answers),
                "keep_alive": keep_alive,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        vectors = resp.json()["embeddings"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return True
    count = len(sources)
    src, out = vectors[:count], vectors[count:]
    for i in range(count):
        own = _cosine(out[i], src[i])
        if any(
            _cosine(out[i], src[j]) > own + ALIGN_MARGIN for j in range(count) if j != i
        ):
            return False
    return True


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
        # ollama_url is operator config, not request input; the request's text
        # travels in the JSON body to that fixed URL, so there is no forgery.
        url = f"{ollama_url}/api/embed"
        body = {"model": EMBED_MODEL, "input": texts, "keep_alive": keep_alive}
        # nosemgrep: python.fastapi.net.tainted-fastapi-http-request-httpx.tainted-fastapi-http-request-httpx
        resp = await client.post(url, json=body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["embeddings"]

    async def judge(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        client: httpx.AsyncClient,
        lang: str,
        source: str,
        value: str,
        glossary: bool = JUDGE_GLOSSARY,
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
        terms = judge_terms(source, lang, languages[lang]) if glossary else ""
        if terms:
            payload["messages"].insert(1, {"role": "system", "content": terms})
        url = f"{ollama_url}/api/chat"  # operator config, as in embed()
        # nosemgrep: python.fastapi.net.tainted-fastapi-http-request-httpx.tainted-fastapi-http-request-httpx
        resp = await client.post(url, json=payload, timeout=timeout)
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

    async def judged(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        client: httpx.AsyncClient,
        req: VerifyRequest,
        i: int,
        cos: Optional[float],
        glossary: bool,
    ) -> dict:
        """One pair's judge verdict as a result row."""
        try:
            ok, reason = await judge(
                client, req.lang, req.items[i].source, req.items[i].value, glossary
            )
        except httpx.HTTPError as exc:
            # One slow or failed judge call must not fail the other 63 pairs
            # in the batch (2026-10-10: a ReadTimeout while a translation run
            # shared the GPU turned a whole batch into a 500).  "retry" leaves
            # the pair unverified for the next run.
            return {
                "ok": False,
                "retry": True,
                "cos": cos,
                "reason": f"judge unavailable: {type(exc).__name__}",
            }
        return {
            "ok": ok,
            "cos": cos,
            "judge": True,
            "reason": "" if ok else f"meaning: {reason or 'judge said no'}",
        }

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
        glossary = JUDGE_GLOSSARY if req.glossary is None else req.glossary
        async with httpx.AsyncClient() as client:
            if to_embed and req.judge_only:
                for i in to_embed:
                    results[i] = await judged(client, req, i, None, glossary)
            elif to_embed:
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
                        results[i] = await judged(client, req, i, cos, glossary)
        return {"verifier": VERIFIER_VERSION, "results": results}

    return router
