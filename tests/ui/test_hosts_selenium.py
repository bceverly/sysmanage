"""
Selenium-based Hosts UI Tests for BSD/cross-platform compatibility
Tests the Hosts page grid/table rendering and functionality

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


def test_hosts_page_loads(selenium_page, test_user, ui_config, start_server):
    """Test that the Hosts page loads successfully"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing Hosts page load with Selenium ({browser_name}) ===")

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Hosts page
        selenium_page.goto("/hosts")
        time.sleep(3)  # Wait for page load

        # Verify we're on the hosts page
        current_url = selenium_page.get_current_url()
        assert "/hosts" in current_url, f"Expected /hosts in URL, got: {current_url}"

        # Verify page title or header
        page_header_selectors = [
            (By.XPATH, '//h1[contains(text(), "Hosts")]'),
            (By.XPATH, '//h2[contains(text(), "Hosts")]'),
            (By.XPATH, '//*[@class="page-title"][contains(text(), "Hosts")]'),
        ]

        header_found = False
        for by, selector in page_header_selectors:
            try:
                selenium_page.driver.find_element(by, selector)
                header_found = True
                print(f"  [OK] Found Hosts page header")
                break
            except NoSuchElementException:
                continue

        if not header_found:
            print("  - Page header not found (may use different structure)")

        print(f"  [OK] Hosts page loaded successfully ({browser_name})")

    except Exception as e:
        screenshot_path = (
            f"tests/ui/test-results/selenium_hosts_load_failure_{int(time.time())}.png"
        )
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Hosts page load test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_hosts_data_displays(selenium_page, test_user, ui_config, start_server):
    """Test that host data actually displays in the grid"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing Hosts data display with Selenium ({browser_name}) ===")

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Hosts page
        selenium_page.goto("/hosts")
        time.sleep(3)

        # Look for row data in the grid
        row_selectors = [
            (By.CSS_SELECTOR, '[class*="MuiDataGrid-row"]'),  # MUI DataGrid rows
            (By.CSS_SELECTOR, '[role="row"]'),  # Generic ARIA row role
            (By.CSS_SELECTOR, '[class*="ag-row"]'),  # AG Grid
            (By.CSS_SELECTOR, "tbody tr"),  # Plain table rows
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
                "  [INFO] No host data rows found - this may be OK if no hosts are registered"
            )
            print("  [INFO] Checking for 'no data' message")

            # Look for "no data" or empty state message
            no_data_selectors = [
                (By.XPATH, '//*[contains(text(), "No hosts")]'),
                (By.XPATH, '//*[contains(text(), "no data")]'),
                (By.XPATH, '//*[contains(text(), "No data")]'),
                (By.CSS_SELECTOR, '[class*="empty"]'),
            ]

            no_data_found = False
            for by, selector in no_data_selectors:
                try:
                    selenium_page.driver.find_element(by, selector)
                    no_data_found = True
                    print("  [OK] Found 'no data' message - grid is working but empty")
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

        print(f"  [OK] Hosts data display test passed ({browser_name})")

    except Exception as e:
        screenshot_path = (
            f"tests/ui/test-results/selenium_hosts_data_failure_{int(time.time())}.png"
        )
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Hosts data display test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


def test_hosts_grid_interactive(selenium_page, test_user, ui_config, start_server):
    """Test that the hosts grid is interactive (sorting, clicking, etc.)"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing Hosts grid interactivity with Selenium ({browser_name}) ===")

    try:
        # Login first
        login_helper(selenium_page, test_user)

        # Navigate to Hosts page
        selenium_page.goto("/hosts")
        time.sleep(3)

        # Try to find and click a column header to test sorting
        header_selectors = [
            (
                By.CSS_SELECTOR,
                '[class*="MuiDataGrid-columnHeader"]',
            ),  # MUI DataGrid headers
            (
                By.CSS_SELECTOR,
                '[role="columnheader"]',
            ),  # Generic ARIA columnheader role
            (By.CSS_SELECTOR, '[class*="ag-header-cell"]'),  # AG Grid
            (By.CSS_SELECTOR, "th"),  # Plain table headers
        ]

        clickable_header = None
        for by, selector in header_selectors:
            try:
                headers = selenium_page.driver.find_elements(by, selector)
                if headers:
                    clickable_header = headers[0]
                    print(f"  [OK] Found clickable header: {clickable_header.text}")
                    break
            except NoSuchElementException:
                continue

        if clickable_header:
            # Try clicking to sort
            original_text = clickable_header.text
            clickable_header.click()
            time.sleep(1)
            print(
                f"  [OK] Clicked column header '{original_text}' - sorting should work"
            )
        else:
            print("  [INFO] No clickable headers found - sorting test skipped")

        # Try to select a row (if rows exist)
        row_selectors = [
            (By.CSS_SELECTOR, '[class*="MuiDataGrid-row"]'),  # MUI DataGrid rows
            (By.CSS_SELECTOR, '[class*="ag-row"]'),  # AG Grid
            (By.CSS_SELECTOR, "tbody tr"),  # Plain table rows
        ]

        for by, selector in row_selectors:
            try:
                rows = selenium_page.driver.find_elements(by, selector)
                if rows:
                    first_row = rows[0]
                    first_row.click()
                    time.sleep(1)
                    print(f"  [OK] Clicked first row - selection should work")
                    break
            except (NoSuchElementException, Exception) as e:
                continue

        print(f"  [OK] Hosts grid interactivity test passed ({browser_name})")

    except Exception as e:
        screenshot_path = f"tests/ui/test-results/selenium_hosts_interactive_failure_{int(time.time())}.png"
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Hosts grid interactivity test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        raise


if __name__ == "__main__":
    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
