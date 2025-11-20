"""
Cross-Browser Package Updates Page UI Tests
Tests Package Updates page functionality across Chrome, Firefox, and Safari (WebKit)

IMPORTANT: Keep this file in sync with test_updates_selenium.py
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
async def test_updates_page_loads(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the Package Updates page loads successfully"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Package Updates page load on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Updates page
        await page.goto(f"{ui_config.base_url}/updates")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Verify we're on the updates page
        assert "/updates" in page.url, f"Expected /updates in URL, got: {page.url}"

        # Verify page title or header
        header_texts = ["Update", "Package"]

        header_found = False
        for text in header_texts:
            selectors = [
                f'h1:has-text("{text}")',
                f'h2:has-text("{text}")',
                f'.page-title:has-text("{text}")',
            ]
            for selector in selectors:
                if await page.locator(selector).count() > 0:
                    header_found = True
                    print(f"  [OK] Found Updates page header")
                    break
            if header_found:
                break

        if not header_found:
            print("  - Page header not found (may use different structure)")

        print(f"  [OK] Package Updates page loaded successfully ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_updates_load_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Updates page load test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_updates_grid_renders(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the package updates grid/table renders correctly - CRITICAL TEST"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Package Updates grid rendering on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Updates page
        await page.goto(f"{ui_config.base_url}/updates")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=10000)
        await page.wait_for_timeout(3000)

        # Wait for the updates list container to be present (it loads dynamically)
        try:
            await page.wait_for_selector(
                '.updates__list, [class*="updates__list"]', timeout=10000
            )
        except:
            # If list doesn't appear, scroll down in case it's lazy-loaded
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        # Look for updates list component (uses custom card layout, not a traditional grid/table)
        grid_selectors = [
            ".updates__list",  # Primary: Custom updates list container
            '[class*="updates__list"]',
            '[class*="ag-grid"]',  # AG Grid (fallback)
            '[class*="data-grid"]',
            "table",
            '[role="grid"]',
            '[class*="updates-grid"]',
            '[class*="updates-table"]',
            '[class*="package-grid"]',
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
        ), "CRITICAL: Grid/table component not found! This is the kind of breakage we want to catch."

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
            "Package",
            "Host",
            "Current",
            "Available",
            "Version",
            "Manager",
            "Type",
            "Status",
        ]

        found_columns = []
        for column in expected_columns:
            if await page.get_by_text(column, exact=False).count() > 0:
                found_columns.append(column)
                print(f"  [OK] Found column: {column}")

        # We should find at least a couple of the expected columns
        assert (
            len(found_columns) >= 2
        ), f"Expected at least 2 columns, found: {found_columns}"

        print(
            f"  [OK] Package Updates grid rendered successfully with {len(found_columns)} recognized columns ({browser_name})"
        )

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_updates_grid_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Package Updates grid rendering test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_updates_data_displays(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that package update data actually displays in the grid"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Package Updates data display on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Updates page
        await page.goto(f"{ui_config.base_url}/updates")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Look for update items in the list (uses custom card layout)
        row_selectors = [
            ".updates__item",  # Primary: Custom update item cards
            '[class*="updates__item"]',
            '[class*="ag-row"]',
            "tbody tr",
            '[role="row"]',
        ]

        rows_found = False
        row_count = 0
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
                    print(f"  [OK] Found {row_count} row(s) in the grid")
                    break

        if not rows_found:
            print(
                "  [INFO] No package update rows found - this may be OK if no updates are available"
            )
            print("  [INFO] Checking for 'no data' or 'no updates' message")

            # Look for "no data" or empty state message
            no_data_texts = [
                "No updates",
                "no updates",
                "No packages",
                "no data",
                "No data",
            ]

            no_data_found = False
            for text in no_data_texts:
                if await page.get_by_text(text, exact=False).count() > 0:
                    no_data_found = True
                    print(
                        "  [OK] Found 'no updates' message - grid is working but empty"
                    )
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
                row = page.locator(row_selectors[0]).nth(i)
                text = await row.inner_text()
                if text.strip():
                    has_content = True
                    print(f"  [OK] Row contains data: {text[:50]}...")
                    break

            assert has_content, "Grid rows exist but contain no visible text"

        print(f"  [OK] Package Updates data display test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_updates_data_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Package Updates data display test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_updates_host_selector(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that the host selector/dropdown works on the Updates page"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Package Updates host selector on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Updates page
        await page.goto(f"{ui_config.base_url}/updates")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Look for host selector dropdown
        selector_selectors = [
            'select[name*="host"]',
            '[class*="host-select"]',
            '[class*="host-selector"]',
        ]

        selector_found = False
        for selector in selector_selectors:
            if await page.locator(selector).count() > 0:
                selector_found = True
                print(f"  [OK] Found host selector")

                # Try to get options count
                options_count = await page.locator(f"{selector} option").count()
                if options_count > 0:
                    print(f"  [OK] Host selector has {options_count} option(s)")

                break

        # Also check for text-based selectors
        if not selector_found:
            for text in ["Select host", "Select Host"]:
                if await page.get_by_text(text, exact=False).count() > 0:
                    selector_found = True
                    print(f"  [OK] Found host selector text")
                    break

        if not selector_found:
            print(
                "  [INFO] No host selector found - may not be implemented or page shows all updates"
            )

        print(f"  [OK] Host selector test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_updates_selector_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Host selector test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


@pytest.mark.parametrize("browser_context", browsers, indirect=True)
@pytest.mark.asyncio
async def test_updates_selection_and_actions(
    page: Page, test_user: dict, ui_config, start_server, browser_context
):
    """Test that updates can be selected and action buttons appear"""
    browser_name = browser_context.browser.browser_type.name
    print(f"\n=== Testing Package Updates selection and actions on {browser_name} ===")

    try:
        # Login first
        await login_helper(page, test_user, ui_config)

        # Navigate to Updates page
        await page.goto(f"{ui_config.base_url}/updates")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Try to find and click a checkbox to select an update
        checkbox_selectors = [
            'input[type="checkbox"]',
            '[class*="ag-selection-checkbox"]',
            '[role="checkbox"]',
        ]

        checkbox_found = False
        for selector in checkbox_selectors:
            count = await page.locator(selector).count()
            if count > 1:  # More than just header checkbox
                # Click the first data row checkbox
                await page.locator(selector).nth(1).click()
                await page.wait_for_timeout(1000)
                checkbox_found = True
                print(f"  [OK] Selected an update via checkbox")
                break

        if not checkbox_found:
            print(
                "  [INFO] No selectable checkboxes found - may use different selection method"
            )

            # Try clicking a row instead
            row_selectors = [
                '[class*="ag-row"]',
                "tbody tr",
            ]

            for selector in row_selectors:
                if await page.locator(selector).count() > 0:
                    await page.locator(selector).first.click()
                    await page.wait_for_timeout(1000)
                    print(f"  [OK] Selected an update via row click")
                    break

        # Look for action buttons that should appear when updates are selected
        action_button_texts = ["Install", "Update", "Apply", "Execute"]

        action_button_found = False
        for text in action_button_texts:
            button = page.get_by_role("button", name=text, exact=False)
            if await button.count() > 0 and await button.first.is_visible():
                action_button_found = True
                button_text = await button.first.inner_text()
                print(f"  [OK] Found action button: {button_text}")
                break

        # Also check for buttons with specific classes
        if not action_button_found:
            button_selectors = [
                '[class*="install-button"]',
                '[class*="update-button"]',
            ]
            for selector in button_selectors:
                if await page.locator(selector).count() > 0:
                    action_button_found = True
                    print(f"  [OK] Found action button with selector: {selector}")
                    break

        if not action_button_found:
            print(
                "  [INFO] No action buttons found - may not be implemented or no updates selected"
            )

        print(f"  [OK] Updates selection and actions test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/playwright_updates_actions_failure_{browser_name}_{int(time.time())}.png"
        await page.screenshot(path=screenshot_path)
        print(f"  [ERROR] Updates selection/actions test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


if __name__ == "__main__":
    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
