"""
UI Tests Configuration
Loads both Selenium and Playwright fixtures to support running all UI tests together.
"""

# Load Selenium fixtures first (provides: selenium_page, browser_driver, chrome_driver, vite_warmup)
from tests.ui.conftest_selenium import *  # noqa: F401,F403

# Load Playwright fixtures (provides: page, browser_context, playwright_instance)
# This will override shared fixtures (ui_config, start_server, database_session, test_user)
# which is fine since they have the same implementation
try:
    from tests.ui.conftest_playwright import *  # noqa: F401,F403
except ImportError:
    # Playwright not installed - Selenium fixtures will still work
    pass
