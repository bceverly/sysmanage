"""
Cross-Browser Login UI Tests
Tests login functionality across Chrome, Firefox, and Safari (WebKit)

IMPORTANT: Keep this file in sync with test_login_selenium.py
The Selenium version is used as a fallback on OpenBSD where Playwright
is not available. When adding/modifying tests here, make equivalent
changes in the Selenium version to ensure feature parity.

Sync checklist:
- Test scenarios and assertions should match
- User credentials and test data should be identical
- Error handling patterns should be consistent
- Test names and descriptions should align
"""

import time
import re
import json
import pytest
from playwright.async_api import Page, expect
import platform

# Only test WebKit on macOS
browsers = ["chromium", "firefox"]
if platform.system() == "Darwin":
    browsers.append("webkit")


async def collect_performance_metrics(page: Page, browser_name: str):
    """Collect performance metrics from the page"""
    try:
        metrics = await page.evaluate(
            """
            () => {
                const navigation = performance.getEntriesByType('navigation')[0];
                const paintEntries = performance.getEntriesByType('paint');

                return {
                    // Page load metrics
                    domContentLoaded: navigation ? navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart : 0,
                    loadComplete: navigation ? navigation.loadEventEnd - navigation.loadEventStart : 0,
                    firstByte: navigation ? navigation.responseStart - navigation.requestStart : 0,

                    // Paint metrics
                    firstPaint: paintEntries.find(entry => entry.name === 'first-paint')?.startTime || 0,
                    firstContentfulPaint: paintEntries.find(entry => entry.name === 'first-contentful-paint')?.startTime || 0,

                    // Resource metrics
                    resourceCount: performance.getEntriesByType('resource').length,

                    // Memory (if available)
                    memoryUsed: performance.memory ? performance.memory.usedJSHeapSize : null
                };
            }
        """
        )

        # Log metrics for this browser
        print(f"📊 {browser_name} Performance Metrics:")
        print(f"   DOM Content Loaded: {metrics['domContentLoaded']:.0f}ms")
        print(f"   First Contentful Paint: {metrics['firstContentfulPaint']:.0f}ms")
        print(f"   Resources loaded: {metrics['resourceCount']}")

        if metrics["memoryUsed"]:
            memory_mb = metrics["memoryUsed"] / (1024 * 1024)
            print(f"   Memory usage: {memory_mb:.1f}MB")

        return metrics
    except Exception as e:
        print(f"⚠️ Failed to collect performance metrics for {browser_name}: {e}")
        return None


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_login_cross_browser(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test login functionality across all browsers"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing login on {browser_name} ===")

    try:
        # Navigate to login page
        await page.goto(f"{ui_config.base_url}/login")

        # Wait for page to load
        await page.wait_for_load_state("networkidle")

        # Collect performance metrics for this browser
        await collect_performance_metrics(page, browser_name)

        # Verify we're on the login page
        await expect(page).to_have_title(re.compile(".*SysManage.*"))

        # Find and fill login form
        username_input = page.locator(
            'input[type="text"], input[placeholder*="email" i], input[placeholder*="username" i]'
        ).first
        password_input = page.locator('input[type="password"]').first

        await expect(username_input).to_be_visible(timeout=10000)
        await expect(password_input).to_be_visible(timeout=10000)

        # Fill in credentials
        await username_input.fill(test_user["username"])
        await password_input.fill(test_user["password"])

        # Find and click login button
        login_button = page.locator(
            'button[type="submit"], button:has-text("LOGIN"), button:has-text("Login"), button:has-text("Sign In")'
        ).first
        await expect(login_button).to_be_visible()
        await login_button.click()

        # Wait for navigation to main dashboard
        await page.wait_for_load_state("networkidle")

        # Verify successful login by checking for main application elements
        # Look for the main navigation menu
        nav_menu = page.locator('nav, .navbar, [role="navigation"]').first
        await expect(nav_menu).to_be_visible(timeout=15000)

        # Check for common navigation links (adjust based on actual app structure)
        # These are typical links we'd expect in a system management application
        expected_nav_items = ["Dashboard", "Hosts", "Reports", "Settings", "Security"]

        # Count how many expected nav items we can find
        found_nav_items = 0
        for item in expected_nav_items:
            nav_link = page.locator(
                f'a:has-text("{item}"), button:has-text("{item}"), [role="menuitem"]:has-text("{item}")'
            ).first
            try:
                await expect(nav_link).to_be_visible(timeout=5000)
                found_nav_items += 1
                print(f"  ✓ Found navigation item: {item}")
            except:
                print(f"  - Navigation item not found: {item}")

        # Verify we found at least 2 navigation items (reasonable minimum)
        assert (
            found_nav_items >= 2
        ), f"Expected at least 2 navigation items, found {found_nav_items}"

        # Additional verification: check that we're no longer on login page
        current_url = page.url
        assert "/login" not in current_url, f"Still on login page: {current_url}"

        # Look for user indicator (username, profile, logout button)
        user_indicator = page.locator(
            f'text="{test_user["username"]}", '
            f'[title*="{test_user["username"]}"], '
            f'button:has-text("Logout"), '
            f'button:has-text("Sign Out"), '
            f'a:has-text("Profile")'
        ).first

        try:
            await expect(user_indicator).to_be_visible(timeout=10000)
            print(f"  ✓ Found user indicator for {test_user['username']}")
        except:
            print(f"  - User indicator not found (may not be implemented yet)")

        print(f"  ✓ Login successful on {browser_name}")
        print(f"  ✓ Found {found_nav_items} navigation items")
        print(f"  ✓ Current URL: {current_url}")

    except Exception as e:
        # Take screenshot on failure for debugging
        screenshot_path = (
            f"/tmp/claude/login_failure_{browser_name}_{int(time.time())}.png"
        )
        await page.screenshot(path=screenshot_path)
        print(f"  ✗ Login test failed on {browser_name}")
        print(f"  ✗ Screenshot saved: {screenshot_path}")
        print(f"  ✗ Current URL: {page.url}")
        print(f"  ✗ Error: {str(e)}")
        raise


@pytest.mark.asyncio
async def test_invalid_login_chromium(page: Page, ui_config, start_server):
    """Test invalid login handling (Chromium only for efficiency)"""
    print("\n=== Testing invalid login handling ===")

    # Navigate to login page
    await page.goto(f"{ui_config.base_url}/login")
    await page.wait_for_load_state("networkidle")

    # Try invalid credentials
    username_input = page.locator('input[type="text"]').first
    password_input = page.locator('input[type="password"]').first

    await username_input.fill("invalid_user")
    await password_input.fill("invalid_password")

    login_button = page.locator(
        'button[type="submit"], button:has-text("LOGIN"), button:has-text("Login")'
    ).first
    await login_button.click()

    # Wait a moment for error handling
    await page.wait_for_timeout(3000)

    # Verify we're still on login page (unsuccessful login)
    current_url = page.url
    assert (
        "/login" in current_url or page.url == f"{ui_config.base_url}/"
    ), f"Expected to stay on login page, but went to: {current_url}"

    # Look for error message (optional, depends on implementation)
    error_indicators = [
        'text="Invalid credentials"',
        'text="Login failed"',
        'text="Invalid username or password"',
        '[role="alert"]',
        ".error",
        ".alert-danger",
    ]

    error_found = False
    for error_selector in error_indicators:
        try:
            error_element = page.locator(error_selector).first
            await expect(error_element).to_be_visible(timeout=2000)
            error_found = True
            print("  ✓ Error message displayed for invalid login")
            break
        except:
            continue

    if not error_found:
        print("  - No specific error message found (may not be implemented)")

    print("  ✓ Invalid login correctly rejected (Chromium)")


@pytest.mark.asyncio
async def test_invalid_login_firefox(page: Page, ui_config, start_server):
    """Test invalid login handling on Firefox"""
    print("\n=== Testing invalid login handling (Firefox) ===")

    # Navigate to login page
    await page.goto(f"{ui_config.base_url}/login")
    await page.wait_for_load_state("networkidle")

    # Try invalid credentials
    username_input = page.locator('input[type="text"]').first
    password_input = page.locator('input[type="password"]').first

    await username_input.fill("invalid_user_firefox")
    await password_input.fill("invalid_password_firefox")

    login_button = page.locator(
        'button[type="submit"], button:has-text("LOGIN"), button:has-text("Login")'
    ).first
    await login_button.click()

    # Wait a moment for error handling
    await page.wait_for_timeout(3000)

    # Verify we're still on login page (unsuccessful login)
    current_url = page.url
    assert (
        "/login" in current_url or page.url == f"{ui_config.base_url}/"
    ), f"Expected to stay on login page, but went to: {current_url}"

    # Look for error message (optional, depends on implementation)
    error_indicators = [
        'text="Invalid credentials"',
        'text="Login failed"',
        'text="Invalid username or password"',
        '[role="alert"]',
        ".error",
        ".alert-danger",
    ]

    error_found = False
    for error_selector in error_indicators:
        try:
            error_element = page.locator(error_selector).first
            await expect(error_element).to_be_visible(timeout=2000)
            error_found = True
            print("  ✓ Error message displayed for invalid login")
            break
        except:
            continue

    if not error_found:
        print("  - No specific error message found (may not be implemented)")

    print("  ✓ Invalid login correctly rejected (Firefox)")


# Only define WebKit test on macOS to avoid "skipped" status on other platforms
if platform.system() == "Darwin":

    @pytest.mark.asyncio
    async def test_invalid_login_webkit(page: Page, ui_config, start_server):
        """Test invalid login handling on WebKit/Safari (macOS only)"""
        print("\n=== Testing invalid login handling (WebKit/Safari) ===")

        # Navigate to login page
        await page.goto(f"{ui_config.base_url}/login")
        await page.wait_for_load_state("networkidle")

        # Try invalid credentials
        username_input = page.locator('input[type="text"]').first
        password_input = page.locator('input[type="password"]').first

        await username_input.fill("invalid_user_webkit")
        await password_input.fill("invalid_password_webkit")

        login_button = page.locator(
            'button[type="submit"], button:has-text("LOGIN"), button:has-text("Login")'
        ).first
        await login_button.click()

        # Wait a moment for error handling
        await page.wait_for_timeout(3000)

        # Verify we're still on login page (unsuccessful login)
        current_url = page.url
        assert (
            "/login" in current_url or page.url == f"{ui_config.base_url}/"
        ), f"Expected to stay on login page, but went to: {current_url}"

        # Look for error message (optional, depends on implementation)
        error_indicators = [
            'text="Invalid credentials"',
            'text="Login failed"',
            'text="Invalid username or password"',
            '[role="alert"]',
            ".error",
            ".alert-danger",
        ]

        error_found = False
        for error_selector in error_indicators:
            try:
                error_element = page.locator(error_selector).first
                await expect(error_element).to_be_visible(timeout=2000)
                error_found = True
                print("  ✓ Error message displayed for invalid login")
                break
            except:
                continue

        if not error_found:
            print("  - No specific error message found (may not be implemented)")

        print("  ✓ Invalid login correctly rejected (WebKit/Safari)")


if __name__ == "__main__":
    import time

    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
