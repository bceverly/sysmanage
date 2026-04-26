#!/usr/bin/env python3
"""
Performance Regression Detection Script
Analyzes performance test results and detects regressions with tolerance bands
"""

import json
import os
import platform
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path


# For each metric we track, which direction is bad?
#   "higher" -> a regression occurs when current is meaningfully GREATER than baseline
#              (latency, error rate, memory use, page-load time)
#   "lower"  -> a regression occurs when current is meaningfully LESS than baseline
#              (throughput, requests/sec)
# Anything not in the table defaults to "higher" (the conservative choice for
# perf metrics — most of what we record is latency-shaped).
METRIC_BAD_DIRECTION = {
    # Artillery-side metrics
    "response_time_p95": "higher",
    "response_time_p99": "higher",
    "response_time_mean": "higher",
    "response_time_median": "higher",
    "error_rate": "higher",
    "requests_per_second": "lower",
    # Playwright-side metrics
    "dom_content_loaded": "higher",
    "load_complete": "higher",
    "first_byte": "higher",
    "first_contentful_paint": "higher",
    "first_paint": "higher",
    "memory_used": "higher",
    # resource_count is informational; treat any change as fine.
    "resource_count": None,
}

# p99 latency is dominated by the slowest single request in the window —
# one cold-start outlier can swing it 5-10x even when the rest of the run
# is fine. Give it a much wider per-metric tolerance so it doesn't fail
# every fresh-backend run; p95 + mean still catch real regressions.
PER_METRIC_TOLERANCE_OVERRIDE = {
    "response_time_p99": 100,  # %
    "linux_response_time_p99": 100,
    "darwin_response_time_p99": 100,
    "windows_response_time_p99": 100,
}


class PerformanceRegessionDetector:
    """Detects performance regressions using statistical analysis"""

    def __init__(self, tolerance_percentage=15, history_window=10):
        """
        Initialize the regression detector

        Args:
            tolerance_percentage: Allowed percentage deviation from baseline
            history_window: Number of recent runs to consider for baseline
        """
        self.tolerance_percentage = tolerance_percentage
        self.history_window = history_window
        self.performance_history_file = "performance-history.json"

    def load_performance_history(self):
        """Load historical performance data"""
        if os.path.exists(self.performance_history_file):
            try:
                with open(self.performance_history_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print("⚠️ Could not load performance history, starting fresh")

        return {"runs": []}

    def save_performance_history(self, history):
        """Save performance history to file"""
        try:
            with open(self.performance_history_file, 'w') as f:
                json.dump(history, f, indent=2)
            print(f"[INFO] Performance history saved to {self.performance_history_file}")
        except Exception as e:
            print(f"[ERROR] Failed to save performance history: {e}")

    def calculate_baseline(self, metric_history):
        """Calculate baseline using rolling average of recent runs"""
        if len(metric_history) < 2:
            return None, None

        # Use recent runs for baseline calculation
        recent_values = metric_history[-self.history_window:]

        if len(recent_values) < 2:
            return recent_values[0], 0

        baseline = statistics.mean(recent_values)
        std_dev = statistics.stdev(recent_values) if len(recent_values) > 1 else 0

        return baseline, std_dev

    def check_regression(self, current_value, baseline, std_dev, metric_name=None):
        """
        Check if current value represents a regression.

        Direction-aware: for "higher-is-bad" metrics (latency, error rate),
        only an INCREASE counts as a regression — a decrease is improvement
        and is reported as such. Likewise for "lower-is-bad" metrics
        (throughput), only a decrease is bad.

        Anything outside the configured tolerance still gets logged so the
        operator sees big swings, but only the bad-direction case actually
        fails the run.
        """
        if baseline is None:
            return False, "No baseline available"

        # Calculate percentage deviation (handle zero baseline)
        if baseline == 0:
            # If baseline is 0, treat any non-zero current value as establishing a new baseline
            if current_value == 0:
                deviation = 0  # Both are zero, no deviation
            else:
                # First measurement, treat as establishing baseline
                deviation = 0
        else:
            deviation = abs(current_value - baseline) / baseline * 100

        # Use tolerance percentage or 2 standard deviations, whichever is more generous.
        # Per-metric overrides exist for famously noisy measures (p99).
        tolerance_by_percentage = PER_METRIC_TOLERANCE_OVERRIDE.get(
            metric_name, self.tolerance_percentage,
        )
        tolerance_by_stddev = (
            (2 * std_dev / baseline * 100) if baseline > 0 else float("inf")
        )
        effective_tolerance = max(tolerance_by_percentage, tolerance_by_stddev)

        if deviation <= effective_tolerance:
            return False, f"{deviation:.1f}% deviation (within {effective_tolerance:.1f}% tolerance)"

        is_increase = current_value > baseline
        direction_word = "increase" if is_increase else "decrease"

        # Direction-aware verdict.
        bad_direction = METRIC_BAD_DIRECTION.get(metric_name, "higher")
        if bad_direction is None:
            # Informational metric — always pass.
            return False, (
                f"{deviation:.1f}% {direction_word} (informational metric)"
            )
        is_regression = (
            (bad_direction == "higher" and is_increase)
            or (bad_direction == "lower" and not is_increase)
        )
        if is_regression:
            return True, f"{deviation:.1f}% {direction_word} (threshold: {effective_tolerance:.1f}%)"
        # Bigger-than-threshold move in the GOOD direction — improvement, not a regression.
        return False, (
            f"{deviation:.1f}% {direction_word} — improvement vs baseline "
            f"(threshold: {effective_tolerance:.1f}%)"
        )

    def analyze_playwright_results(self, results_file):
        """Analyze Playwright performance results"""
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Could not load Playwright results: {e}")
            return {}

        metrics = {}

        # Extract key performance metrics
        if 'navigation' in data:
            nav = data['navigation']
            metrics['dom_content_loaded'] = nav.get('domContentLoaded', 0)
            metrics['load_complete'] = nav.get('loadComplete', 0)
            metrics['first_byte'] = nav.get('firstByte', 0)

        if 'paint' in data:
            paint = data['paint']
            metrics['first_contentful_paint'] = paint.get('firstContentfulPaint', 0)
            metrics['first_paint'] = paint.get('firstPaint', 0)

        if 'resources' in data and 'total' in data['resources']:
            metrics['resource_count'] = data['resources']['total']

        if 'memory' in data and data['memory']:
            metrics['memory_used'] = data['memory']['used']

        return metrics

    def analyze_artillery_results(self, results_file):
        """Analyze Artillery load test results.

        Modern Artillery (>= 2.x) reports use this aggregate shape:
            aggregate.summaries.http.response_time -> {min, max, mean, median,
                                                      p50, p75, p90, p95, p99, p999}
            aggregate.rates.http.request_rate     -> single number (rps)
            aggregate.counters.http.codes.NNN     -> per-status counts
            aggregate.counters.vusers.{created,failed,completed}
            aggregate.counters.http.{requests,responses}
        """
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Could not load Artillery results: {e}")
            return {}

        metrics = {}
        agg = data.get('aggregate', {})
        if not agg:
            return metrics

        summaries = agg.get('summaries', {})
        rates = agg.get('rates', {})
        counters = agg.get('counters', {})

        # Response times
        rt = summaries.get('http.response_time', {})
        if rt:
            metrics['response_time_p95'] = rt.get('p95', 0)
            metrics['response_time_p99'] = rt.get('p99', 0)
            metrics['response_time_median'] = rt.get('median', rt.get('p50', 0))
            metrics['response_time_mean'] = rt.get('mean', 0)

        # Request rate (modern artillery exposes a single number, not a dict)
        if 'http.request_rate' in rates:
            rps_value = rates['http.request_rate']
            # Defensive: older artillery 1.x exposed this as {mean: N}
            metrics['requests_per_second'] = (
                rps_value if isinstance(rps_value, (int, float))
                else rps_value.get('mean', 0)
            )

        # Error rate (% of HTTP responses that were not 2xx)
        responses = counters.get('http.responses', 0)
        ok_2xx = sum(v for k, v in counters.items() if k.startswith('http.codes.2'))
        if responses > 0:
            metrics['error_rate'] = ((responses - ok_2xx) / responses) * 100

        return metrics

    def run_regression_analysis(self, current_results):
        """Run complete regression analysis on current results"""
        history = self.load_performance_history()

        # Add current run to history
        current_run = {
            'timestamp': datetime.now().isoformat(),
            'metrics': current_results
        }

        regressions_found = []
        performance_summary = []

        print("\n[INFO] Performance Regression Analysis")
        print("=" * 50)

        for metric_name, current_value in current_results.items():
            # Get historical values for this metric
            metric_history = []
            for run in history['runs']:
                if metric_name in run['metrics']:
                    metric_history.append(run['metrics'][metric_name])

            # Calculate baseline
            baseline, std_dev = self.calculate_baseline(metric_history)

            # Check for regression (direction-aware per metric)
            is_regression, details = self.check_regression(
                current_value, baseline, std_dev, metric_name=metric_name,
            )

            # Format metric name for display
            display_name = metric_name.replace('_', ' ').title()

            if baseline is not None:
                print(f"{display_name}:")
                print(f"  Current: {current_value:.2f}")
                print(f"  Baseline: {baseline:.2f}")
                print(f"  Status: {details}")

                if is_regression:
                    print(f"  ⚠️ REGRESSION DETECTED!")
                    regressions_found.append({
                        'metric': metric_name,
                        'current': current_value,
                        'baseline': baseline,
                        'details': details
                    })
                else:
                    print(f"  ✅ Within acceptable range")
            else:
                print(f"{display_name}: {current_value:.2f} (establishing baseline)")

            print()

            performance_summary.append({
                'metric': metric_name,
                'current': current_value,
                'baseline': baseline,
                'is_regression': is_regression,
                'details': details
            })

        # Add current run to history
        history['runs'].append(current_run)

        # Keep only recent runs to prevent unbounded growth
        if len(history['runs']) > self.history_window * 2:
            history['runs'] = history['runs'][-self.history_window * 2:]

        # Save updated history
        self.save_performance_history(history)

        return regressions_found, performance_summary


def main():
    """Main function to run performance regression analysis"""
    detector = PerformanceRegessionDetector(tolerance_percentage=15)

    # Collect results from different sources
    all_metrics = {}

    # Analyze Playwright results
    playwright_file = "performance-results.json"
    if os.path.exists(playwright_file):
        print("[INFO] Analyzing Playwright performance results...")
        playwright_metrics = detector.analyze_playwright_results(playwright_file)
        all_metrics.update(playwright_metrics)

    # Analyze Artillery results.
    # CI may produce per-OS files (artillery-report-Linux.json, etc.) when
    # aggregating runs across multiple OS runners. Local
    # 'make test-performance' produces the canonical artillery-report.json.
    # Check both, prefixing with the host OS for the canonical file so
    # baselines stay comparable per platform.
    artillery_candidates = [
        ("artillery-report.json", platform.system().lower()),
    ] + [
        (f"artillery-report-{n}.json", n.lower())
        for n in ("Linux", "macOS", "Windows")
    ]
    for artillery_file, os_label in artillery_candidates:
        if os.path.exists(artillery_file):
            print(f"⚡ Analyzing Artillery results from {artillery_file}...")
            artillery_metrics = detector.analyze_artillery_results(artillery_file)
            prefixed_metrics = {f"{os_label}_{k}": v for k, v in artillery_metrics.items()}
            all_metrics.update(prefixed_metrics)

    if not all_metrics:
        # Treat absence of data as a real failure — the calling Makefile target
        # ran us as part of a "performance tests passed" gate, and reporting
        # success when we couldn't analyze anything would silently mask a
        # broken artillery run, missing report file, or upstream collection
        # failure (which we've been bitten by before — see git history for
        # the artillery-scenarios-misconfigured incident).
        print(
            "[ERROR] No performance results found to analyze.\n"
            "        Expected at least one of:\n"
            "          - performance-results.json (Playwright timings), or\n"
            "          - artillery-report.json (modern artillery output), or\n"
            "          - artillery-report-{Linux,macOS,Windows}.json (CI per-OS).\n"
            "        Check that the upstream test step actually ran and produced\n"
            "        a report. Failing this check intentionally so the Makefile\n"
            "        target does not report success on a vacuous run."
        )
        return 1

    # Run regression analysis
    regressions, summary = detector.run_regression_analysis(all_metrics)

    # Generate summary report
    print("\n📈 Performance Analysis Summary")
    print("=" * 50)
    print(f"Total metrics analyzed: {len(all_metrics)}")
    print(f"Regressions detected: {len(regressions)}")

    if regressions:
        print("\n⚠️ Performance Regressions Found:")
        for regression in regressions:
            print(f"  - {regression['metric']}: {regression['details']}")

        # Return error code for CI/CD
        return 1
    else:
        print("\n✅ No performance regressions detected!")
        return 0


if __name__ == "__main__":
    sys.exit(main())