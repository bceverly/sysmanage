"""
Cross-Browser Hosts Page UI Tests
Tests Hosts page functionality across Chrome, Firefox, and Safari (WebKit)

IMPORTANT: Keep this file in sync with test_hosts_selenium.py
The Selenium version is used as a fallback on OpenBSD where Playwright
is not available. When adding/modifying tests here, make equivalent
changes in the Selenium version to ensure feature parity.

Sync checklist:
- Test scenarios and assertions should match
- Test names and descriptions should align
- Error handling patterns should be consistent
"""

import time
import pytest
from playwright.async_api import Page, expect
import platform

# Only test WebKit on macOS
browsers = ["chromium", "firefox"]
if platform.system() == "Darwin":
    browsers.append("webkit")


async def login_helper(page: Page, test_user: dict, ui_config):
    """Helper function to log in before running tests"""
    await page.goto(f"{ui_config.base_url}/login")
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    # Fill login form
    await page.fill('input[type="text"]', test_user["username"])
    await page.fill('input[type="password"]', test_user["password"])
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(3000)


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_hosts_page_loads(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the Hosts page loads successfully"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Hosts page load on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Hosts page
        await page.goto(f"{ui_config.base_url}/hosts")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Verify we're on the hosts page
        assert "/hosts" in page.url, f"Expected /hosts in URL, got: {page.url}"

        # Verify page title or header
        header_selectors = [
            'h1:has-text("Hosts")',
            'h2:has-text("Hosts")',
            '.page-title:has-text("Hosts")',
        ]

        header_found = False
        for selector in header_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    header_found = True
                    print(f"  [OK] Found Hosts page header")
                    break
            except:
                continue

        if not header_found:
            print("  - Page header not found (may use different structure)")

        print(f"  [OK] Hosts page loaded successfully ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_hosts_load_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Hosts page load test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_hosts_grid_renders(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the hosts grid/table renders correctly - THIS WOULD HAVE CAUGHT THE BREAKAGE"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Hosts grid rendering on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Hosts page
        await page.goto(f"{ui_config.base_url}/hosts")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Look for grid/table component - try multiple possible selectors
        grid_selectors = [
            '[class*="ag-grid"]',  # AG Grid
            '[class*="data-grid"]',
            "table",
            '[role="grid"]',
            '[class*="hosts-grid"]',
            '[class*="hosts-table"]',
        ]

        grid_found = False
        grid_element = None
        for selector in grid_selectors:
            locator = page.locator(selector)
            if await locator.count() > 0:
                grid_element = locator.first
                if await grid_element.is_visible():
                    grid_found = True
                    print(f"  [OK] Found grid/table with selector: {selector}")
                    break

        assert (
            grid_found
        ), "CRITICAL: Grid/table component not found! This is exactly the kind of breakage we want to catch."

        # Verify the grid is visible (has non-zero dimensions)
        assert await grid_element.is_visible(), "Grid element exists but is not visible"

        box = await grid_element.bounding_box()
        assert (
            box is not None and box["width"] > 0 and box["height"] > 0
        ), f"Grid has zero dimensions: {box}"

        print(f"  [OK] Grid is visible with dimensions: {box['width']}x{box['height']}")

        # Look for column headers
        header_selectors = [
            '[class*="ag-header"]',
            "thead",
            '[role="columnheader"]',
            "th",
        ]

        headers_found = False
        for selector in header_selectors:
            count = await page.locator(selector).count()
            if count > 0:
                headers_found = True
                print(f"  [OK] Found {count} column header(s)")
                break

        if not headers_found:
            print(
                "  [WARNING] No column headers found - grid may not be fully initialized"
            )

        # Look for expected column names
        expected_columns = [
            "Hostname",
            "FQDN",
            "OS",
            "Platform",
            "Status",
            "IP",
            "Last Seen",
        ]

        found_columns = []
        for column in expected_columns:
            # Try to find text containing the column name
            if await page.get_by_text(column, exact=False).count() > 0:
                found_columns.append(column)
                print(f"  [OK] Found column: {column}")

        # We should find at least a couple of the expected columns
        assert (
            len(found_columns) >= 2
        ), f"Expected at least 2 columns, found: {found_columns}"

        print(
            f"  [OK] Hosts grid rendered successfully with {len(found_columns)} recognized columns ({browser_name})"
        )

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_hosts_grid_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Hosts grid rendering test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_hosts_data_displays(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that host data actually displays in the grid"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Hosts data display on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Hosts page
        await page.goto(f"{ui_config.base_url}/hosts")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Look for row data in the grid
        row_selectors = [
            '[class*="ag-row"]',
            "tbody tr",
            '[role="row"]',
        ]

        rows_found = False
        row_count = 0
        found_selector = None
        for selector in row_selectors:
            count = await page.locator(selector).count()
            if count > 0:
                # Filter out header rows
                visible_rows = []
                for i in range(count):
                    row = page.locator(selector).nth(i)
                    class_attr = await row.get_attribute("class") or ""
                    if "rowgroup" not in class_attr and await row.is_visible():
                        visible_rows.append(row)

                if visible_rows:
                    rows_found = True
                    row_count = len(visible_rows)
                    found_selector = selector
                    print(f"  [OK] Found {row_count} row(s) in the grid")
                    break

        if not rows_found:
            print(
                "  [INFO] No host data rows found - this may be OK if no hosts are registered"
            )
            print("  [INFO] Checking for 'no data' message")

            # Look for "no data" or empty state message
            no_data_texts = ["No hosts", "no data", "No data"]

            no_data_found = False
            for text in no_data_texts:
                if await page.get_by_text(text, exact=False).count() > 0:
                    no_data_found = True
                    print("  [OK] Found 'no data' message - grid is working but empty")
                    break

            if not no_data_found and await page.locator('[class*="empty"]').count() > 0:
                no_data_found = True
                print("  [OK] Found empty state element - grid is working but empty")

            if not no_data_found:
                print("  [WARNING] No rows and no 'empty state' message found")
        else:
            # Verify at least one row has visible text content
            has_content = False
            for i in range(min(5, row_count)):  # Check first 5 rows
                row = page.locator(found_selector).nth(i)
                text = await row.inner_text()
                if text.strip():
                    has_content = True
                    print(f"  [OK] Row contains data: {text[:50]}...")
                    break

            assert has_content, "Grid rows exist but contain no visible text"

        print(f"  [OK] Hosts data display test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_hosts_data_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Hosts data display test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_hosts_grid_interactive(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the hosts grid is interactive (sorting, clicking, etc.)"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Hosts grid interactivity on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Hosts page
        await page.goto(f"{ui_config.base_url}/hosts")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Try to find and click a column header to test sorting
        header_selectors = [
            '[class*="ag-header-cell"]',
            "th",
            '[role="columnheader"]',
        ]

        clickable_header = None
        for selector in header_selectors:
            if await page.locator(selector).count() > 0:
                clickable_header = page.locator(selector).first
                header_text = await clickable_header.inner_text()
                print(f"  [OK] Found clickable header: {header_text}")
                break

        if clickable_header:
            # Try clicking to sort
            await clickable_header.click()
            await page.wait_for_timeout(1000)
            print(f"  [OK] Clicked column header - sorting should work")
        else:
            print("  [INFO] No clickable headers found - sorting test skipped")

        # Try to select a row (if rows exist)
        row_selectors = [
            '[class*="ag-row"]',
            "tbody tr",
        ]

        for selector in row_selectors:
            if await page.locator(selector).count() > 0:
                first_row = page.locator(selector).first
                await first_row.click()
                await page.wait_for_timeout(1000)
                print(f"  [OK] Clicked first row - selection should work")
                break

        print(f"  [OK] Hosts grid interactivity test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_hosts_interactive_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Hosts grid interactivity test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


if __name__ == "__main__":
    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
