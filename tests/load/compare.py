"""
Compare two load-test result JSON files and flag regressions.

Invoked by .github/workflows/load-tests.yml after a load run finishes:
the workflow downloads the previous tag's artifact, then runs

    python tests/load/compare.py --baseline old.json --candidate new.json [--threshold 0.20]

Comparison rules (per scenario, matched by ``name``):

  - ``p95_ms``        regression if candidate > baseline * (1 + threshold)
  - ``error_rate``    regression if candidate > baseline + 0.05  (absolute,
                                  since rates near 0 explode under % math)
  - ``throughput_rps``regression if candidate < baseline * (1 - threshold)
  - ``breakpoint_msgs_per_sec``  (parsed from notes; ws-backpressure only)
                       regression if candidate < baseline * (1 - threshold)

Default threshold is 20 %.  Override per-CI via --threshold.

Exit codes:

  0  — no regressions detected.
  2  — one or more regressions found (workflow surfaces this as a job
       failure / PR check fail).  Same code as run.py uses for SLA
       violations so the workflow's existing handling fits.
  1  — input error (missing files, malformed JSON, etc.).

Output:  human-readable diff to stdout, plus a one-line summary that
the workflow uses for PR comments.
"""

# pylint: disable=missing-function-docstring

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read {path}: {e}", file=sys.stderr)
        return None


def _scenarios_by_name(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {s.get("name"): s for s in report.get("scenarios", []) if s.get("name")}


def _breakpoint_from_notes(s: Dict[str, Any]) -> Optional[int]:
    """ws-backpressure stores breakpoint_msgs_per_sec=N in notes."""
    for note in s.get("notes", []) or []:
        m = re.match(r"breakpoint_msgs_per_sec=(\d+)", str(note))
        if m:
            return int(m.group(1))
    return None


def _check_metric(
    name: str,
    metric: str,
    baseline: Optional[float],
    candidate: Optional[float],
    direction: str,
    threshold: float,
) -> Optional[Tuple[str, float]]:
    """Return (regression_message, percent_change) if regressed, else None.

    direction='up' means HIGHER candidate is bad (latency, error rate).
    direction='down' means LOWER candidate is bad (throughput, breakpoint).
    """
    if baseline is None or candidate is None:
        return None
    if metric == "error_rate":
        # Absolute, not relative.  An error rate going from 0.001 to 0.04
        # is +3,900 % but only +0.039 absolute — the latter is what we care.
        delta = candidate - baseline
        if delta > 0.05:
            return (
                f"{name}: error_rate {baseline:.2%} → {candidate:.2%} "
                f"(+{delta * 100:.1f} pp, threshold +5 pp)",
                delta * 100,
            )
        return None

    if baseline == 0:
        return None  # avoid divide-by-zero; can't compute regression %

    if direction == "up":
        ratio = (candidate - baseline) / baseline
        if ratio > threshold:
            return (
                f"{name}: {metric} {baseline:.2f} → {candidate:.2f} "
                f"(+{ratio * 100:.1f} %, threshold +{threshold * 100:.0f} %)",
                ratio * 100,
            )
    else:  # down
        ratio = (baseline - candidate) / baseline
        if ratio > threshold:
            return (
                f"{name}: {metric} {baseline:.2f} → {candidate:.2f} "
                f"(-{ratio * 100:.1f} %, threshold -{threshold * 100:.0f} %)",
                -ratio * 100,
            )
    return None


def _compare_scenario(
    name: str,
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    threshold: float,
) -> List[str]:
    """Return list of regression strings for this scenario (empty = clean)."""
    regressions: List[str] = []

    for metric, direction in (
        ("p95_ms", "up"),
        ("error_rate", "up"),
        ("throughput_rps", "down"),
    ):
        hit = _check_metric(
            name,
            metric,
            baseline.get(metric),
            candidate.get(metric),
            direction,
            threshold,
        )
        if hit:
            regressions.append(hit[0])

    bp_base = _breakpoint_from_notes(baseline)
    bp_cand = _breakpoint_from_notes(candidate)
    if bp_base is not None and bp_cand is not None:
        hit = _check_metric(
            name, "breakpoint_msgs_per_sec", bp_base, bp_cand, "down", threshold
        )
        if hit:
            regressions.append(hit[0])

    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two load-test result JSON files for regression."
    )
    parser.add_argument("--baseline", required=True, help="Previous run JSON")
    parser.add_argument("--candidate", required=True, help="Current run JSON")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.20,
        help="Relative regression threshold (default 0.20 = 20 percent)",
    )
    args = parser.parse_args()

    baseline = _load(args.baseline)
    candidate = _load(args.candidate)
    if baseline is None or candidate is None:
        return 1

    base_by_name = _scenarios_by_name(baseline)
    cand_by_name = _scenarios_by_name(candidate)

    common = sorted(set(base_by_name) & set(cand_by_name))
    only_baseline = sorted(set(base_by_name) - set(cand_by_name))
    only_candidate = sorted(set(cand_by_name) - set(base_by_name))

    print("=== Load-test regression check ===")
    print(f"Baseline:  {args.baseline}  ({len(base_by_name)} scenarios)")
    print(f"Candidate: {args.candidate}  ({len(cand_by_name)} scenarios)")
    print(
        f"Threshold: {args.threshold * 100:.0f} % (relative); +5 pp (error_rate, absolute)"
    )
    print()

    if only_baseline:
        print(
            f"Note: {len(only_baseline)} scenario(s) in baseline but not candidate: "
            f"{', '.join(only_baseline)}"
        )
    if only_candidate:
        print(
            f"Note: {len(only_candidate)} scenario(s) new in candidate: "
            f"{', '.join(only_candidate)}"
        )

    if not common:
        # Nothing comparable — informational, not a failure.  This
        # happens when the baseline ran a different scenario set
        # (e.g., before the WS reliability suite was added).
        print("\nNo scenarios in common; nothing to compare.  Exiting clean.")
        return 0

    all_regressions: List[str] = []
    for name in common:
        regs = _compare_scenario(
            name, base_by_name[name], cand_by_name[name], args.threshold
        )
        if regs:
            all_regressions.extend(regs)

    if all_regressions:
        print(f"\n{len(all_regressions)} REGRESSION(S):")
        for r in all_regressions:
            print(f"  - {r}")
        print(f"\nFAIL: load-test regression vs baseline.")
        return 2

    print(f"\nPASS: no regressions across {len(common)} scenario(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
