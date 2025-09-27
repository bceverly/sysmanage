"""
Performance testing for SysManage UI using Playwright
Measures page load times, resource loading, and rendering performance
"""

import json
import platform
import time
from datetime import datetime
import pytest
from playwright.async_api import Page


class TestSysManagePerformance:
    """Performance tests for SysManage web interface"""

    @pytest.mark.asyncio
    async def test_login_page_performance(self, page: Page, ui_config):
        """Test login page load performance and Core Web Vitals"""
        print("\n=== Testing Login Page Performance ===")

        # Start timing
        start_time = time.time()

        # Navigate to login page
        response = await page.goto(f"https://localhost:{ui_config.port}")

        # Wait for page to be fully loaded
        await page.wait_for_load_state("networkidle")

        # Measure page load time
        load_time = time.time() - start_time
        print(f"🕐 Total page load time: {load_time:.2f}s")

        # Collect performance metrics
        performance_metrics = await page.evaluate(
            """
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                const paintEntries = performance.getEntriesByType('paint');

                return {
                    // Navigation timing
                    domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                    loadComplete: navigation.loadEventEnd - navigation.loadEventStart,

                    // Resource timing
                    resourceCount: performance.getEntriesByType('resource').length,

                    // Paint timing
                    firstPaint: paintEntries.find(entry => entry.name === 'first-paint')?.startTime || 0,
                    firstContentfulPaint: paintEntries.find(entry => entry.name === 'first-contentful-paint')?.startTime || 0,

                    // Memory usage (if available)
                    memoryUsed: performance.memory ? performance.memory.usedJSHeapSize : null,
                    memoryTotal: performance.memory ? performance.memory.totalJSHeapSize : null
                };
            }
        """
        )

        print(f"🎨 First Paint: {performance_metrics['firstPaint']:.2f}ms")
        print(
            f"🎨 First Contentful Paint: {performance_metrics['firstContentfulPaint']:.2f}ms"
        )
        print(f"📄 DOM Content Loaded: {performance_metrics['domContentLoaded']:.2f}ms")
        print(f"🌐 Resources loaded: {performance_metrics['resourceCount']}")

        if performance_metrics["memoryUsed"]:
            memory_mb = performance_metrics["memoryUsed"] / (1024 * 1024)
            print(f"💾 Memory usage: {memory_mb:.2f}MB")

        # Performance budgets (fail if exceeded)
        assert (
            load_time < 5.0
        ), f"Page load time {load_time:.2f}s exceeds budget of 5.0s"
        assert (
            performance_metrics["firstContentfulPaint"] < 2000
        ), f"FCP {performance_metrics['firstContentfulPaint']:.2f}ms exceeds budget of 2000ms"
        assert (
            performance_metrics["domContentLoaded"] < 1500
        ), f"DCL {performance_metrics['domContentLoaded']:.2f}ms exceeds budget of 1500ms"

        print("✅ Login page performance within acceptable limits")

    @pytest.mark.asyncio
    async def test_login_flow_performance(self, page: Page, ui_config, test_user):
        """Test login flow performance including form submission"""
        print("\n=== Testing Login Flow Performance ===")

        # Navigate to login page
        await page.goto(f"https://localhost:{ui_config.port}")
        await page.wait_for_load_state("networkidle")

        # Measure login form interaction
        start_time = time.time()

        # Fill login form
        await page.fill('input[name="username"]', test_user["username"])
        await page.fill('input[name="password"]', test_user["password"])

        # Submit and measure response time
        form_start = time.time()
        await page.click('button[type="submit"]')

        # Wait for navigation or error message
        try:
            await page.wait_for_url("**/dashboard**", timeout=5000)
            login_success = True
            navigation_time = time.time() - form_start
            print(f"✅ Login successful in {navigation_time:.2f}s")
        except:
            login_success = False
            # Look for error message instead
            await page.wait_for_selector(".error-message, .alert-error", timeout=2000)
            error_time = time.time() - form_start
            print(f"❌ Login failed (expected) in {error_time:.2f}s")
            navigation_time = error_time

        total_flow_time = time.time() - start_time
        print(f"🕐 Total login flow time: {total_flow_time:.2f}s")

        # Performance budget for login flow
        assert (
            navigation_time < 3.0
        ), f"Login response time {navigation_time:.2f}s exceeds budget of 3.0s"
        assert (
            total_flow_time < 5.0
        ), f"Total login flow {total_flow_time:.2f}s exceeds budget of 5.0s"

        print("✅ Login flow performance within acceptable limits")

    @pytest.mark.asyncio
    async def test_network_performance(self, page: Page, ui_config):
        """Test network request performance and resource loading"""
        print("\n=== Testing Network Performance ===")

        # Track network requests
        network_requests = []

        async def track_request(request):
            network_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "start_time": time.time(),
                }
            )

        async def track_response(response):
            # Find matching request
            for req in network_requests:
                if req["url"] == response.url and "response_time" not in req:
                    req["response_time"] = time.time() - req["start_time"]
                    req["status"] = response.status
                    req["size"] = (
                        len(await response.body()) if response.status == 200 else 0
                    )
                    break

        page.on("request", track_request)
        page.on("response", track_response)

        # Navigate and collect network metrics
        await page.goto(f"https://localhost:{ui_config.port}")
        await page.wait_for_load_state("networkidle")

        # Remove event listeners
        page.remove_listener("request", track_request)
        page.remove_listener("response", track_response)

        # Analyze network performance
        completed_requests = [req for req in network_requests if "response_time" in req]

        if completed_requests:
            avg_response_time = sum(
                req["response_time"] for req in completed_requests
            ) / len(completed_requests)
            max_response_time = max(req["response_time"] for req in completed_requests)
            total_size = sum(req["size"] for req in completed_requests)

            print(f"🌐 Total requests: {len(completed_requests)}")
            print(f"⚡ Average response time: {avg_response_time:.3f}s")
            print(f"🐌 Slowest request: {max_response_time:.3f}s")
            print(f"📦 Total size: {total_size / 1024:.2f}KB")

            # Find slowest requests
            slow_requests = [
                req for req in completed_requests if req["response_time"] > 1.0
            ]
            if slow_requests:
                print("🐌 Slow requests (>1s):")
                for req in slow_requests:
                    print(
                        f"   {req['method']} {req['url']} - {req['response_time']:.3f}s"
                    )

            # Performance budgets
            assert (
                avg_response_time < 0.5
            ), f"Average response time {avg_response_time:.3f}s exceeds budget of 0.5s"
            assert (
                max_response_time < 2.0
            ), f"Slowest response time {max_response_time:.3f}s exceeds budget of 2.0s"
            assert (
                len(slow_requests) == 0
            ), f"{len(slow_requests)} requests exceeded 1s response time"

            print("✅ Network performance within acceptable limits")
        else:
            print("⚠️ No network requests captured")

    @pytest.mark.asyncio
    async def test_save_performance_results(self, page: Page, ui_config):
        """Save performance test results for CI/CD analysis"""
        print("\n=== Saving Performance Results ===")

        # Collect comprehensive performance data
        performance_data = await page.evaluate(
            """
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                const resources = performance.getEntriesByType('resource');
                const paintEntries = performance.getEntriesByType('paint');

                return {
                    timestamp: new Date().toISOString(),
                    platform: navigator.platform,
                    userAgent: navigator.userAgent,

                    // Navigation metrics
                    navigation: {
                        domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                        loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                        firstByte: navigation.responseStart - navigation.requestStart,
                        domComplete: navigation.domComplete - navigation.navigationStart
                    },

                    // Paint metrics
                    paint: {
                        firstPaint: paintEntries.find(entry => entry.name === 'first-paint')?.startTime || 0,
                        firstContentfulPaint: paintEntries.find(entry => entry.name === 'first-contentful-paint')?.startTime || 0
                    },

                    // Resource summary
                    resources: {
                        total: resources.length,
                        byType: resources.reduce((acc, resource) => {
                            acc[resource.initiatorType] = (acc[resource.initiatorType] || 0) + 1;
                            return acc;
                        }, {}),
                        totalSize: resources.reduce((acc, resource) => acc + (resource.transferSize || 0), 0)
                    },

                    // Memory (if available)
                    memory: window.performance.memory ? {
                        used: performance.memory.usedJSHeapSize,
                        total: performance.memory.totalJSHeapSize,
                        limit: performance.memory.jsHeapSizeLimit
                    } : null
                };
            }
        """
        )

        # Add test environment info
        performance_data["test_environment"] = {
            "python_version": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "test_time": datetime.now().isoformat(),
        }

        # Save to file for CI/CD processing
        results_file = "performance-results.json"
        try:
            with open(results_file, "w") as f:
                json.dump(performance_data, f, indent=2)
            print(f"💾 Performance results saved to {results_file}")
        except Exception as e:
            print(f"⚠️ Failed to save performance results: {e}")

        # Log key metrics for CI/CD
        print("📊 Key Performance Metrics:")
        print(f"   FCP: {performance_data['paint']['firstContentfulPaint']:.0f}ms")
        print(f"   DCL: {performance_data['navigation']['domContentLoaded']:.0f}ms")
        print(f"   Load: {performance_data['navigation']['loadComplete']:.0f}ms")
        print(f"   Resources: {performance_data['resources']['total']}")

        if performance_data["memory"]:
            memory_mb = performance_data["memory"]["used"] / (1024 * 1024)
            print(f"   Memory: {memory_mb:.1f}MB")


# Platform-specific performance tests
if platform.system() == "Darwin":

    class TestSysManagePerformanceMacOS(TestSysManagePerformance):
        """macOS-specific performance tests"""

        @pytest.mark.asyncio
        async def test_webkit_performance(self, page: Page, ui_config):
            """Test performance specifically on WebKit/Safari"""
            print("\n=== Testing WebKit Performance (macOS) ===")

            # This test only runs if we're using WebKit browser
            browser_name = page.context.browser.browser_type.name
            if browser_name == "webkit":
                await page.goto(f"https://localhost:{ui_config.port}")
                await page.wait_for_load_state("networkidle")

                # WebKit-specific metrics
                webkit_metrics = await page.evaluate(
                    r"""
                    () => ({
                        webkitPerformance: window.webkitPerformance ? true : false,
                        safariVersion: navigator.userAgent.includes('Safari') ?
                            navigator.userAgent.match(/Version\/([\d.]+)/)?.[1] : null
                    })
                """
                )

                print(
                    f"🍎 WebKit Performance API available: {webkit_metrics['webkitPerformance']}"
                )
                if webkit_metrics["safariVersion"]:
                    print(f"🍎 Safari version: {webkit_metrics['safariVersion']}")

                print("✅ WebKit performance test completed")
            else:
                print(f"⏭️ Skipping WebKit test (browser: {browser_name})")
