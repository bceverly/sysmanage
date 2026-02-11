"""
UI Tests Configuration
Loads Selenium fixtures for BSD fallback testing (where Playwright is not available).
For Playwright E2E tests, use 'make test-e2e' which runs TypeScript tests in frontend/e2e/.
"""

# Load Selenium fixtures (provides: selenium_page, browser_driver, chrome_driver, vite_warmup)
# Used on BSD systems (OpenBSD, FreeBSD, NetBSD) where Playwright is not supported
from tests.ui.conftest_selenium import *  # noqa: F401,F403
