"""
UI Tests Configuration
Loads Selenium or Playwright fixtures based on test file
"""

import sys

# Determine which fixtures to load based on the test module being run
if any("selenium" in arg for arg in sys.argv):
    # Load Selenium fixtures for Selenium tests
    from tests.ui.conftest_selenium import *  # noqa: F401,F403
elif any("playwright" in arg for arg in sys.argv):
    # Load Playwright fixtures for Playwright tests
    from tests.ui.conftest_playwright import *  # noqa: F401,F403
else:
    # Default to Selenium fixtures (can be changed based on preference)
    from tests.ui.conftest_selenium import *  # noqa: F401,F403
