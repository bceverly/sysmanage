#!/usr/bin/env python3
# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Calibrate the translation verifier's judge (ROADMAP 23.4).

The judge's prompt is calibrated, and a change made without re-measuring once
made it reject 831 of 832 good values.  This measures the judge ALONE (the
service's ``judge_only`` mode skips the embedding bands) on four sets drawn
from a repository's own translations and ledger, with and without the domain
glossary:

  false_alarms  values a human accepted after the judge rejected them (the
                ledger's "human ..." lines whose reason mentions the judge or
                a glossary term) -- correct, so the judge should PASS them;
  good_short    model-verified values of one or two words -- the judge was
                over-strict on short headings;
  good_long     model-verified values of six words or more;
  swapped       a verified value paired with ANOTHER key's English, same
                locale -- wrong, so the judge should REJECT them.

A change is better only if it passes more of the first three WITHOUT passing
more of the fourth.

Usage:
    python3 scripts/i18n_judge_calibrate.py --service http://beast:8766 \\
        [--repo ../sysmanage-docs] [--per-lang 6] [--seed 23]
"""

from __future__ import annotations

import argparse
import importlib
import json
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

SETS = ("false_alarms", "good_short", "good_long", "swapped")
WANT = {"false_alarms": True, "good_short": True, "good_long": True, "swapped": False}
JUDGE_REASONS = ("judge", "glossary", "fleet", "over-strict", "false alarm")


def _load_verifier(repo: Path):
    sys.path.insert(0, str(repo / "scripts"))
    return importlib.import_module("i18n_verify")


def _words(text: str) -> int:
    return len(text.split())


def gather(verifier) -> Tuple[Dict[str, list], Dict[str, list]]:
    """{lang: [(source, value), ...]} model-verified, and human false alarms."""
    allow = verifier.strict.Allow(verifier.strict.ALLOW_FILE)
    ledger = verifier.load_ledger()
    verified: Dict[str, list] = defaultdict(list)
    alarms: Dict[str, list] = defaultdict(list)
    for item in verifier.translated_values(allow):
        if not isinstance(item.value, str):
            continue
        how = ledger.get(verifier.ident(item))
        if how == "model":
            verified[item.lang].append((item.source, item.value))
        elif how and any(word in how.lower() for word in JUDGE_REASONS):
            alarms[item.lang].append((item.source, item.value))
    return verified, alarms


def build_sets(
    verified, alarms, per_lang: int, seed: int
) -> Dict[str, Dict[str, list]]:
    """{set: {lang: [(source, value)]}}, the same sample every run."""
    rng = random.Random(seed)
    out: Dict[str, Dict[str, list]] = {name: {} for name in SETS}
    for lang in sorted(verified):
        pairs = sorted(set(verified[lang]))
        short = [p for p in pairs if _words(p[0]) <= 2]
        long_ = [p for p in pairs if _words(p[0]) >= 6]
        out["good_short"][lang] = rng.sample(short, min(per_lang, len(short)))
        out["good_long"][lang] = rng.sample(long_, min(per_lang, len(long_)))
        donors = rng.sample(pairs, min(per_lang * 2, len(pairs)))
        out["swapped"][lang] = [
            (a[0], b[1])
            for a, b in zip(donors[::2], donors[1::2])
            if a[0].strip().lower() != b[0].strip().lower()
        ]
        out["false_alarms"][lang] = sorted(set(alarms.get(lang, [])))
    return out


def judge(service: str, lang: str, pairs, glossary: bool) -> List[dict]:
    body = json.dumps(
        {
            "lang": lang,
            "items": [{"source": s, "value": v} for s, v in pairs],
            "judge_only": True,
            "glossary": glossary,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{service.rstrip('/')}/verify/batch",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=1800) as resp:  # nosec B310
        return json.loads(resp.read())["results"]


def measure(service, sets, variants) -> Dict[str, Dict[str, list]]:
    """{variant: {set: [row]}} -- every pair judged under every variant."""
    out: Dict[str, Dict[str, list]] = {}
    for variant, glossary in variants:
        out[variant] = {name: [] for name in SETS}
        for name in SETS:
            for lang, pairs in sets[name].items():
                for start in range(0, len(pairs), 32):
                    chunk = pairs[start : start + 32]
                    for (source, value), result in zip(
                        chunk, judge(service, lang, chunk, glossary)
                    ):
                        out[variant][name].append(
                            {"lang": lang, "source": source, "value": value, **result}
                        )
                print(f"  {variant:<12} {name:<13} {lang:<6} done", flush=True)
    return out


def summarize(results) -> str:
    lines = [f"{'set':<13} {'want':<7}" + "".join(f"{v:>16}" for v in results)]
    for name in SETS:
        cells = []
        for variant in results:
            rows = [r for r in results[variant][name] if not r.get("retry")]
            right = sum(1 for r in rows if bool(r["ok"]) == WANT[name])
            cells.append(f"{right}/{len(rows)} right".rjust(16))
        want = "pass" if WANT[name] else "reject"
        lines.append(f"{name:<13} {want:<7}" + "".join(cells))
    return "\n".join(lines)


def flips(results, a: str, b: str) -> List[str]:
    """Pairs the two variants judged differently, for a human to read."""
    out = []
    for name in SETS:
        for left, right in zip(results[a][name], results[b][name]):
            if bool(left["ok"]) != bool(right["ok"]):
                verdict = "now passes" if right["ok"] else "now rejected"
                out.append(
                    f"[{name}] {left['lang']}: {verdict}: {left['source'][:60]!r} -> "
                    f"{left['value'][:60]!r} ({left.get('reason') or right.get('reason')})"
                )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--service", required=True)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--per-lang", type=int, default=6)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--out", type=Path, default=Path("judge-calibration.json"))
    args = parser.parse_args()
    if not args.service.lower().startswith(("http://", "https://")):
        sys.exit("--service must be an http:// or https:// URL")
    verified, alarms = gather(_load_verifier(args.repo.resolve()))
    sets = build_sets(verified, alarms, args.per_lang, args.seed)
    sizes = {name: sum(len(v) for v in sets[name].values()) for name in SETS}
    print(f"{args.repo.resolve().name}: {sizes}", flush=True)
    results = measure(args.service, sets, (("prompt", False), ("+glossary", True)))
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("\n" + summarize(results))
    changed = flips(results, "prompt", "+glossary")
    print(f"\n{len(changed)} pair(s) judged differently with the glossary:")
    print("\n".join(changed) if changed else "  (none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
