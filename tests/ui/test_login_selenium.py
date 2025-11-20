"""
Selenium-based Login UI Tests for OpenBSD
Fallback when Playwright is not available

IMPORTANT: Keep this file in sync with test_login_cross_browser.py
When adding/modifying tests in the Playwright version, make equivalent
changes here to ensure feature parity across platforms.

Sync checklist:
- Test scenarios and assertions should match
- User credentials and test data should be identical
- Error handling patterns should be consistent
- Test names and descriptions should align
"""

import time
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def test_login_selenium(selenium_page, test_user, ui_config, start_server):
    """Test login functionality using Selenium"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing login with Selenium ({browser_name}) ===")

    try:
        # Navigate to login page
        selenium_page.goto("/login")

        # Wait for page body to load
        try:
            selenium_page.wait_for_element_visible(By.CSS_SELECTOR, 'body', timeout=10)
        except TimeoutException:
            print("  [WARNING] Body element not found")

        # Wait for MUI Container to load
        try:
            selenium_page.wait_for_element_visible(By.CSS_SELECTOR, 'form', timeout=10)
            print("  [OK] Login form container loaded")
        except TimeoutException:
            print("  [WARNING] Form element not found, continuing anyway")

        # Additional wait for React/MUI to render
        time.sleep(3)

        # Verify we're on the login page
        title = selenium_page.get_title()
        assert "SysManage" in title, f"Expected SysManage in title, got: {title}"

        # Find and fill login form
        # Try multiple selectors for username/email field (MUI TextField specific)
        username_selectors = [
            (By.CSS_SELECTOR, 'input[id="userid"]'),  # MUI TextField id
            (By.CSS_SELECTOR, 'input[name="userid"]'),  # MUI TextField name
            (By.CSS_SELECTOR, 'input[type="text"]'),  # Fallback
            (By.CSS_SELECTOR, 'input[placeholder*="email" i]'),
            (By.CSS_SELECTOR, 'input[placeholder*="username" i]'),
            (By.CSS_SELECTOR, 'input[name="username"]'),
            (By.CSS_SELECTOR, 'input[name="email"]'),
            (By.CSS_SELECTOR, 'input[autocomplete="email"]'),  # MUI TextField autocomplete
        ]

        username_input = None
        attempted_username_selectors = []
        for by, selector in username_selectors:
            attempted_username_selectors.append(selector)
            try:
                username_input = selenium_page.wait_for_element_visible(
                    by, selector, timeout=5
                )
                print(f"  [OK] Found username field with selector: {selector}")
                break
            except TimeoutException:
                continue

        if username_input is None:
            print(f"  [DEBUG] Failed to find username field. Tried: {', '.join(attempted_username_selectors)}")
            print(f"  [DEBUG] Current URL: {selenium_page.get_current_url()}")

        assert username_input is not None, "Could not find username input field"

        # Find password field (try multiple selectors)
        password_selectors = [
            (By.CSS_SELECTOR, 'input[id="password"]'),  # MUI TextField id
            (By.CSS_SELECTOR, 'input[name="password"]'),  # MUI TextField name
            (By.CSS_SELECTOR, 'input[type="password"]'),  # Standard
        ]

        password_input = None
        for by, selector in password_selectors:
            try:
                password_input = selenium_page.wait_for_element_visible(
                    by, selector, timeout=5
                )
                print(f"  [OK] Found password field with selector: {selector}")
                break
            except TimeoutException:
                continue

        assert password_input is not None, "Could not find password input field"

        # Fill in credentials
        username_input.clear()
        username_input.send_keys(test_user["username"])
        password_input.clear()
        password_input.send_keys(test_user["password"])

        # Find and click login button
        login_button_selectors = [
            (By.CSS_SELECTOR, 'button[type="submit"]'),
            (By.XPATH, '//button[contains(text(), "LOGIN")]'),
            (By.XPATH, '//button[contains(text(), "Login")]'),
            (By.XPATH, '//button[contains(text(), "Sign In")]'),
        ]

        login_button = None
        for by, selector in login_button_selectors:
            try:
                login_button = selenium_page.wait_for_element_clickable(
                    by, selector, timeout=5
                )
                break
            except TimeoutException:
                continue

        assert login_button is not None, "Could not find login button"
        login_button.click()

        # Wait for navigation
        time.sleep(3)

        # Verify successful login by checking for main application elements
        current_url = selenium_page.get_current_url()
        assert "/login" not in current_url, f"Still on login page: {current_url}"

        # Look for navigation menu
        nav_selectors = [
            (By.CSS_SELECTOR, "nav"),
            (By.CSS_SELECTOR, ".navbar"),
            (By.CSS_SELECTOR, '[role="navigation"]'),
        ]

        nav_found = False
        for by, selector in nav_selectors:
            try:
                nav_element = selenium_page.wait_for_element_visible(
                    by, selector, timeout=10
                )
                nav_found = True
                break
            except TimeoutException:
                continue

        assert nav_found, "Could not find navigation menu after login"

        # Check for common navigation links (based on actual app structure from screenshots)
        expected_nav_items = [
            "Dashboard",
            "Hosts",
            "Users",
            "Updates",
            "Reports",
            "Secrets",
            "Scripts",
        ]
        found_nav_items = 0

        for item in expected_nav_items:
            nav_link_selectors = [
                (By.XPATH, f'//a[contains(text(), "{item}")]'),
                (By.XPATH, f'//button[contains(text(), "{item}")]'),
                (By.XPATH, f'//*[@role="menuitem"][contains(text(), "{item}")]'),
            ]

            for by, selector in nav_link_selectors:
                try:
                    selenium_page.driver.find_element(by, selector)
                    found_nav_items += 1
                    print(f"  [OK] Found navigation item: {item}")
                    break
                except NoSuchElementException:
                    continue

        # Verify we found at least 2 navigation items
        assert (
            found_nav_items >= 2
        ), f"Expected at least 2 navigation items, found {found_nav_items}"

        # Look for user indicator
        user_indicator_selectors = [
            (By.XPATH, f'//text()[contains(., "{test_user["username"]}")]'),
            (By.XPATH, f'//*[@title="{test_user["username"]}"]'),
            (By.XPATH, '//button[contains(text(), "Logout")]'),
            (By.XPATH, '//button[contains(text(), "Sign Out")]'),
            (By.XPATH, '//a[contains(text(), "Profile")]'),
        ]

        user_indicator_found = False
        for by, selector in user_indicator_selectors:
            try:
                selenium_page.driver.find_element(by, selector)
                user_indicator_found = True
                print(f"  [OK] Found user indicator")
                break
            except NoSuchElementException:
                continue

        if not user_indicator_found:
            print(f"  - User indicator not found (may not be implemented yet)")

        print(f"  [OK] Login successful with Selenium ({browser_name})")
        print(f"  [OK] Found {found_nav_items} navigation items")
        print(f"  [OK] Current URL: {current_url}")

    except Exception as e:
        # Take screenshot on failure
        screenshot_path = (
            f"tests/ui/test-results/selenium_login_failure_{int(time.time())}.png"
        )
        selenium_page.screenshot(screenshot_path)
        print(f"  [ERROR] Selenium login test failed ({browser_name})")
        print(f"  [ERROR] Screenshot saved: {screenshot_path}")
        print(f"  [ERROR] Current URL: {selenium_page.get_current_url()}")
        print(f"  [ERROR] Error: {str(e)}")
        raise


def test_invalid_login_selenium(selenium_page, ui_config, start_server):
    """Test invalid login handling using Selenium"""
    browser_name = selenium_page.browser_name
    print(f"\n=== Testing invalid login with Selenium ({browser_name}) ===")

    # Navigate to login page
    selenium_page.goto("/login")

    # Wait for form to load
    try:
        selenium_page.wait_for_element_visible(By.CSS_SELECTOR, 'form', timeout=10)
    except TimeoutException:
        pass

    time.sleep(3)  # Extra wait for MUI components

    # Find input fields (MUI TextField selectors)
    username_selectors = [
        (By.CSS_SELECTOR, 'input[id="userid"]'),
        (By.CSS_SELECTOR, 'input[name="userid"]'),
        (By.CSS_SELECTOR, 'input[type="text"]'),
    ]

    username_input = None
    for by, selector in username_selectors:
        try:
            username_input = selenium_page.wait_for_element_visible(by, selector, timeout=5)
            break
        except TimeoutException:
            continue

    if username_input is None:
        raise Exception("Could not find username input field in login form")

    password_selectors = [
        (By.CSS_SELECTOR, 'input[id="password"]'),
        (By.CSS_SELECTOR, 'input[name="password"]'),
        (By.CSS_SELECTOR, 'input[type="password"]'),
    ]

    password_input = None
    for by, selector in password_selectors:
        try:
            password_input = selenium_page.wait_for_element_visible(by, selector, timeout=5)
            break
        except TimeoutException:
            continue

    if password_input is None:
        raise Exception("Could not find password input field in login form")

    # Try invalid credentials
    username_input.clear()
    username_input.send_keys("invalid_user")
    password_input.clear()
    password_input.send_keys("invalid_password")

    # Click login button
    login_button = selenium_page.wait_for_element_clickable(
        By.CSS_SELECTOR, 'button[type="submit"]'
    )
    login_button.click()

    # Wait for response and handle alert if present
    time.sleep(3)

    # Handle alert dialog if present
    try:
        alert = selenium_page.driver.switch_to.alert
        alert_text = alert.text
        print(f"  [OK] Found expected alert: {alert_text}")
        alert.accept()  # Click OK on the alert
        time.sleep(1)  # Wait for alert to be dismissed
    except Exception:
        print("  - No alert found (may use different error display method)")

    # Verify we're still on login page
    current_url = selenium_page.get_current_url()
    assert (
        "/login" in current_url or current_url == f"{ui_config.base_url}/"
    ), f"Expected to stay on login page, but went to: {current_url}"

    # Look for error message
    error_selectors = [
        (By.XPATH, '//*[contains(text(), "Invalid credentials")]'),
        (By.XPATH, '//*[contains(text(), "Login failed")]'),
        (By.XPATH, '//*[contains(text(), "Invalid username or password")]'),
        (By.CSS_SELECTOR, '[role="alert"]'),
        (By.CSS_SELECTOR, ".error"),
        (By.CSS_SELECTOR, ".alert-danger"),
    ]

    error_found = False
    for by, selector in error_selectors:
        try:
            selenium_page.driver.find_element(by, selector)
            error_found = True
            print("  [OK] Error message displayed for invalid login")
            break
        except NoSuchElementException:
            continue

    if not error_found:
        print("  - No specific error message found (may not be implemented)")

    print(f"  [OK] Invalid login correctly rejected (Selenium {browser_name})")


if __name__ == "__main__":
    # For debugging individual tests
    pytest.main([__file__, "-v", "-s"])
