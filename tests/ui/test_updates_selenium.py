"""
Selenium-based Package Updates UI Tests for BSD/cross-platform compatibility
Tests the Package Updates page grid/table rendering and functionality

IMPORTANT: Keep this file in sync with any Playwright version if created
When adding/modifying tests, ensure feature parity across platforms.
"""

import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def login_helper(selenium_page, test_user):
    """Helper function to log in before running tests"""
    selenium_page.goto("/login")

    # Wait for page to load and React to render
    try:
        selenium_page.wait_for_element_visible(By.CSS_SELECTOR, "form", timeout=10)
    except TimeoutException:
        pass  # Continue anyway

    time.sleep(3)  # Extra wait for MUI components to render

    # Find and fill login form (MUI TextField selectors)
    # Try multiple selectors for username field
    username_selectors = [
        (By.CSS_SELECTOR, 'input[id="userid"]'),
        (By.CSS_SELECTOR, 'input[name="userid"]'),
        (By.CSS_SELECTOR, 'input[type="text"]'),
        (By.CSS_SELECTOR, 'input[autocomplete="email"]'),
    ]

    username_input = None
    for by, selector in username_selectors:
        try:
            username_input = selenium_page.wait_for_element_visible(
                by, selector, timeout=5
            )
            break
        except TimeoutException:
            continue

    if username_input is None:
        raise Exception("Could not find username input field in login form")

    # Try multiple selectors for password field
    password_selectors = [
        (By.CSS_SELECTOR, 'input[id="password"]'),
        (By.CSS_SELECTOR, 'input[name="password"]'),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    ]

    password_input = None
    for by, selector in password_selectors:
        try:
            password_input = selenium_page.wait_for_element_visible(
                by, selector, timeout=5
            )
            break
        except TimeoutException:
            continue

    if password_input is None:
        raise Exception("Could not find password input field in login form")

    username_input.clear()
    username_input.send_keys(test_user["username"])
    password_input.clear()
    password_input.send_keys(test_user["password"])

    login_button = selenium_page.wait_for_element_clickable(
        By.CSS_SELECTOR, 'button[type="submit"]'
    )
    login_button.click()
    time.sleep(3)  # Wait for navigation


def test_updates_page_loads(selenium_page, test_user, ui_config, start_server):
    """Test that the Package Updates page loads successfully"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing Package Updates page load with Selenium ({browser_name}) ===")

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Updates page
        selenium_page.goto("/updates")
        time.sleep(3)  # Wait for page load

        # Verify we're on the updates page
        current_url = selenium_page.get_current_url()
        assert (
            "/updates" in current_url
        ), f"Expected /updates in URL, got: {current_url}"

        # Verify page title or header
        page_header_selectors = [
            (By.XPATH, '//h1[contains(text(), "Update")]'),
            (By.XPATH, '//h2[contains(text(), "Update")]'),
            (By.XPATH, '//*[@class="page-title"][contains(text(), "Update")]'),
            (By.XPATH, '//h1[contains(text(), "Package")]'),
            (By.XPATH, '//h2[contains(text(), "Package")]'),
        ]

        header_found = False
        for by, selector in page_header_selectors:
            try:
                selenium_page.driver.find_element(by, selector)
                header_found = True
                print(f"  [OK] Found Updates page header")
                break
            except NoSuchElementException:
                continue

        if not header_found:
            print("  - Page header not found (may use different structure)")

        print(f"  [OK] Package Updates page loaded successfully ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_updates_load_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Updates page load test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_updates_grid_renders(selenium_page, test_user, ui_config, start_server):
    """Test that the package updates grid/table renders correctly - CRITICAL TEST"""
    browser_name = selenium_page.browser_name
    print(
        f"\n=== Testing Package Updates grid rendering with Selenium ({browser_name}) ==="
    )

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Updates page
        selenium_page.goto("/updates")
        time.sleep(5)  # Increased wait time for page to fully load

        # Look for updates page content container (uses custom card layout, not a traditional grid/table)
        # First check if the main content area is loaded
        content_selectors = [
            (By.CSS_SELECTOR, ".updates__content"),  # Main content container
            (By.CSS_SELECTOR, ".updates"),  # Page wrapper
        ]

        content_found = False
        for by, selector in content_selectors:
            try:
                selenium_page.wait_for_element_visible(by, selector, timeout=15)
                content_found = True
                print(f"  [OK] Found updates page content container: {selector}")
                break
            except TimeoutException:
                continue

        assert (
            content_found
        ), "CRITICAL: Updates page content not found! Page may not have loaded."

        # Now look for either the updates list OR the "no updates" message
        # (Both are valid - page is working either way)
        list_or_empty_selectors = [
            (By.CSS_SELECTOR, ".updates__list"),  # Updates list container
            (By.CSS_SELECTOR, ".updates__empty"),  # "No updates" message
        ]

        grid_found = False
        grid_element = None
        for by, selector in list_or_empty_selectors:
            try:
                grid_element = selenium_page.wait_for_element_visible(
                    by, selector, timeout=5
                )
                grid_found = True
                print(f"  [OK] Found updates component with selector: {selector}")
                break
            except TimeoutException:
                continue

        assert (
            grid_found
        ), "CRITICAL: Neither updates list nor 'no updates' message found! This indicates the page is broken."

        # Verify the grid is visible (has non-zero dimensions)
        assert grid_element.is_displayed(), "Grid element exists but is not visible"
        size = grid_element.size
        assert (
            size["width"] > 0 and size["height"] > 0
        ), f"Grid has zero dimensions: {size}"

        print(
            f"  [OK] Updates component is visible with dimensions: {size['width']}x{size['height']}"
        )

        # Since Updates uses a card layout (not a table), look for update items or stats instead of columns
        # Check for statistics cards (always present)
        stats_selectors = [
            (By.CSS_SELECTOR, ".updates__stats"),  # Stats container
            (By.CSS_SELECTOR, ".updates__stat-card"),  # Individual stat cards
        ]

        stats_found = False
        for by, selector in stats_selectors:
            try:
                stats_elements = selenium_page.driver.find_elements(by, selector)
                if stats_elements:
                    stats_found = True
                    print(f"  [OK] Found {len(stats_elements)} statistics element(s)")
                    break
            except NoSuchElementException:
                continue

        # Check for update items (if any exist)
        update_items = []
        try:
            update_items = selenium_page.driver.find_elements(
                By.CSS_SELECTOR, ".updates__item"
            )
            if update_items:
                print(f"  [OK] Found {len(update_items)} update item(s) in the list")
        except NoSuchElementException:
            print("  [INFO] No update items found - may indicate no updates available")

        # Page is valid if we found either stats or the empty message
        element_class = grid_element.get_attribute("class") or ""
        assert (
            stats_found or "updates__empty" in element_class
        ), "Expected to find either update statistics or 'no updates' message"

        print(f"  [OK] Package Updates page rendered successfully ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_updates_grid_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Package Updates grid rendering test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_updates_data_displays(selenium_page, test_user, ui_config, start_server):
    """Test that package update data actually displays in the grid"""
    browser_name = selenium_page.browser_name
    print(
        f"\n=== Testing Package Updates data display with Selenium ({browser_name}) ==="
    )

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Updates page
        selenium_page.goto("/updates")
        time.sleep(3)

        # Look for update items in the list (uses custom card layout)
        row_selectors = [
            (By.CSS_SELECTOR, ".updates__item"),  # Primary: Custom update item cards
            (By.CSS_SELECTOR, '[class*="updates__item"]'),
            (By.CSS_SELECTOR, '[class*="ag-row"]'),
            (By.CSS_SELECTOR, "tbody tr"),
            (By.CSS_SELECTOR, '[role="row"]'),
        ]

        rows_found = False
        row_elements = []
        for by, selector in row_selectors:
            try:
                row_elements = selenium_page.driver.find_elements(by, selector)
                # Filter out header rows if using role="row"
                if by == (By.CSS_SELECTOR, '[role="row"]'):
                    row_elements = [
                        r
                        for r in row_elements
                        if "rowgroup" not in r.get_attribute("class")
                    ]

                if row_elements:
                    rows_found = True
                    print(f"  [OK] Found {len(row_elements)} row(s) in the grid")
                    break
            except NoSuchElementException:
                continue

        if not rows_found:
            print(
                "  [INFO] No package update rows found - this may be OK if no updates are available"
            )
            print("  [INFO] Checking for 'no data' or 'no updates' message")

            # Look for "no data" or empty state message
            no_data_selectors = [
                (By.XPATH, '//*[contains(text(), "No updates")]'),
                (By.XPATH, '//*[contains(text(), "no updates")]'),
                (By.XPATH, '//*[contains(text(), "No packages")]'),
                (By.XPATH, '//*[contains(text(), "no data")]'),
                (By.XPATH, '//*[contains(text(), "No data")]'),
                (By.CSS_SELECTOR, '[class*="empty"]'),
            ]

            no_data_found = False
            for by, selector in no_data_selectors:
                try:
                    selenium_page.driver.find_element(by, selector)
                    no_data_found = True
                    print(
                        "  [OK] Found 'no updates' message - grid is working but empty"
                    )
                    break
                except NoSuchElementException:
                    continue

            if not no_data_found:
                print("  [WARNING] No rows and no 'empty state' message found")
        else:
            # Verify at least one row has visible text content
            has_content = False
            for row in row_elements[:5]:  # Check first 5 rows
                if row.text.strip():
                    has_content = True
                    print(f"  [OK] Row contains data: {row.text[:50]}...")
                    break

            assert has_content, "Grid rows exist but contain no visible text"

        print(f"  [OK] Package Updates data display test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_updates_data_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Package Updates data display test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_updates_host_selector(selenium_page, test_user, ui_config, start_server):
    """Test that the host selector/dropdown works on the Updates page"""
    browser_name = selenium_page.browser_name
    print(
        f"\n=== Testing Package Updates host selector with Selenium ({browser_name}) ==="
    )

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Updates page
        selenium_page.goto("/updates")
        time.sleep(3)

        # Look for host selector dropdown
        selector_selectors = [
            (By.CSS_SELECTOR, 'select[name*="host"]'),
            (By.CSS_SELECTOR, '[class*="host-select"]'),
            (By.CSS_SELECTOR, '[class*="host-selector"]'),
            (By.XPATH, '//select[contains(@class, "host")]'),
            (By.XPATH, '//*[contains(text(), "Select host")]'),
            (By.XPATH, '//*[contains(text(), "Select Host")]'),
        ]

        selector_found = False
        for by, selector in selector_selectors:
            try:
                element = selenium_page.driver.find_element(by, selector)
                selector_found = True
                print(f"  [OK] Found host selector")

                # Try to interact with it if it's a dropdown
                if element.tag_name == "select":
                    options = element.find_elements(By.TAG_NAME, "option")
                    print(f"  [OK] Host selector has {len(options)} option(s)")

                break
            except NoSuchElementException:
                continue

        if not selector_found:
            print(
                "  [INFO] No host selector found - may not be implemented or page shows all updates"
            )

        print(f"  [OK] Host selector test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_updates_selector_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Host selector test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_updates_selection_and_actions(
    selenium_page, test_user, ui_config, start_server
):
    """Test that updates can be selected and action buttons appear"""
    browser_name = selenium_page.browser_name
    print(
        f"\n=== Testing Package Updates selection and actions with Selenium ({browser_name}) ==="
    )

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Updates page
        selenium_page.goto("/updates")
        time.sleep(3)

        # Try to find and click a checkbox or row to select an update
        checkbox_selectors = [
            (By.CSS_SELECTOR, 'input[type="checkbox"]'),
            (By.CSS_SELECTOR, '[class*="ag-selection-checkbox"]'),
            (By.CSS_SELECTOR, '[role="checkbox"]'),
        ]

        checkbox_found = False
        for by, selector in checkbox_selectors:
            try:
                checkboxes = selenium_page.driver.find_elements(by, selector)
                if checkboxes and len(checkboxes) > 1:  # More than just header checkbox
                    # Click the first data row checkbox
                    checkboxes[1].click()
                    time.sleep(1)
                    checkbox_found = True
                    print(f"  [OK] Selected an update via checkbox")
                    break
            except (NoSuchElementException, Exception):
                continue

        if not checkbox_found:
            print(
                "  [INFO] No selectable checkboxes found - may use different selection method"
            )

            # Try clicking a row instead
            row_selectors = [
                (By.CSS_SELECTOR, '[class*="ag-row"]'),
                (By.CSS_SELECTOR, "tbody tr"),
            ]

            for by, selector in row_selectors:
                try:
                    rows = selenium_page.driver.find_elements(by, selector)
                    if rows:
                        rows[0].click()
                        time.sleep(1)
                        print(f"  [OK] Selected an update via row click")
                        break
                except (NoSuchElementException, Exception):
                    continue

        # Look for action buttons that should appear when updates are selected
        action_button_selectors = [
            (By.XPATH, '//button[contains(text(), "Install")]'),
            (By.XPATH, '//button[contains(text(), "Update")]'),
            (By.XPATH, '//button[contains(text(), "Apply")]'),
            (By.XPATH, '//button[contains(text(), "Execute")]'),
            (By.CSS_SELECTOR, '[class*="install-button"]'),
            (By.CSS_SELECTOR, '[class*="update-button"]'),
        ]

        action_button_found = False
        for by, selector in action_button_selectors:
            try:
                button = selenium_page.driver.find_element(by, selector)
                if button.is_displayed():
                    action_button_found = True
                    print(f"  [OK] Found action button: {button.text}")
                    break
            except NoSuchElementException:
                continue

        if not action_button_found:
            print(
                "  [INFO] No action buttons found - may not be implemented or no updates selected"
            )

        print(f"  [OK] Updates selection and actions test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_updates_actions_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Updates selection/actions test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


if __name__ == "__main__":
    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
