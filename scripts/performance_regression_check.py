#!/usr/bin/env python3
"""
Performance Regression Detection Script
Analyzes performance test results and detects regressions with tolerance bands
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import statistics


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

    def check_regression(self, current_value, baseline, std_dev):
        """Check if current value represents a regression"""
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

        # Use tolerance percentage or 2 standard deviations, whichever is more generous
        tolerance_by_percentage = self.tolerance_percentage
        tolerance_by_stddev = (2 * std_dev / baseline * 100) if baseline > 0 else float('inf')

        effective_tolerance = max(tolerance_by_percentage, tolerance_by_stddev)

        if deviation > effective_tolerance:
            direction = "increase" if current_value > baseline else "decrease"
            return True, f"{deviation:.1f}% {direction} (threshold: {effective_tolerance:.1f}%)"

        return False, f"{deviation:.1f}% deviation (within {effective_tolerance:.1f}% tolerance)"

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
        """Analyze Artillery load test results"""
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Could not load Artillery results: {e}")
            return {}

        metrics = {}

        # Extract Artillery metrics
        if 'aggregate' in data:
            agg = data['aggregate']

            # Response times
            if 'latency' in agg:
                lat = agg['latency']
                metrics['response_time_p95'] = lat.get('p95', 0)
                metrics['response_time_p99'] = lat.get('p99', 0)
                metrics['response_time_median'] = lat.get('median', 0)

            # Request rates
            if 'rps' in agg:
                metrics['requests_per_second'] = agg['rps'].get('mean', 0)

            # Error rates
            if 'errors' in agg:
                total_requests = agg.get('requestsCompleted', 0) + agg.get('errors', 0)
                if total_requests > 0:
                    metrics['error_rate'] = (agg['errors'] / total_requests) * 100

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

            # Check for regression
            is_regression, details = self.check_regression(current_value, baseline, std_dev)

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

    # Analyze Artillery results for each OS
    for os_name in ['Linux', 'macOS', 'Windows']:
        artillery_file = f"artillery-report-{os_name}.json"
        if os.path.exists(artillery_file):
            print(f"⚡ Analyzing Artillery results for {os_name}...")
            artillery_metrics = detector.analyze_artillery_results(artillery_file)
            # Prefix metrics with OS name to avoid conflicts
            prefixed_metrics = {f"{os_name.lower()}_{k}": v for k, v in artillery_metrics.items()}
            all_metrics.update(prefixed_metrics)

    if not all_metrics:
        print("⚠️ No performance results found to analyze")
        return 0

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