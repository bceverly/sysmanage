# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""
UI Tests Configuration
Loads Selenium fixtures for BSD fallback testing (where Playwright is not available).
For Playwright E2E tests, use 'make test-e2e' which runs TypeScript tests in frontend/e2e/.
"""

# Load Selenium fixtures (provides: selenium_page, browser_driver, chrome_driver, vite_warmup)
# Used on BSD systems (OpenBSD, FreeBSD, NetBSD) where Playwright is not supported
from tests.ui.conftest_selenium import *  # noqa: F401,F403
