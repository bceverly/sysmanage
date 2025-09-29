"""
Selenium-based test configuration for OpenBSD
Fallback when Playwright is not available

This file provides the same fixtures as conftest.py but using Selenium instead of Playwright

Cross-browser testing requirements:
- Chrome/Chromium: Requires chromedriver (usually: doas pkg_add chromedriver)
- Firefox: Requires geckodriver (usually: doas pkg_add firefox-geckodriver)

If either browser/driver is missing, tests will be skipped for that browser.
"""

import os
import time
import pytest
import yaml
import uuid
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.persistence.models.core import User


def load_sysmanage_config():
    """Load SysManage configuration using the same logic as backend/config/config.py"""
    # Check for system config first, then fall back to development config
    if os.name == "nt":  # Windows
        config_path = r"C:\ProgramData\SysManage\sysmanage.yaml"
    else:  # Unix-like (Linux, macOS, BSD)
        config_path = "/etc/sysmanage.yaml"

    # Fallback to development config if system config doesn't exist
    if not os.path.exists(config_path) and os.path.exists("sysmanage-dev.yaml"):
        config_path = "sysmanage-dev.yaml"

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

            # Apply defaults just like the main config
            if "host" not in config["api"]:
                config["api"]["host"] = "localhost"
            if "port" not in config["api"]:
                config["api"]["port"] = 8443
            if "host" not in config["webui"]:
                config["webui"]["host"] = "localhost"
            if "port" not in config["webui"]:
                config["webui"]["port"] = 8080

            return config
    except Exception as e:
        # Fall back to hardcoded defaults if config loading fails
        print(f"Warning: Could not load config file: {e}")
        return {
            "api": {"host": "localhost", "port": 8080},
            "webui": {"host": "localhost", "port": 3000},
        }


def resolve_host_for_client(config_host):
    """Resolve host for client connections, same logic as start.sh generate_urls function"""
    if config_host == "0.0.0.0":
        # When bound to 0.0.0.0, prefer localhost for client connections
        # (could also use hostname like start.sh, but localhost is safer for tests)
        return "localhost"
    else:
        # Use the configured host directly
        return config_host


class UIConfig:
    def __init__(self):
        config = load_sysmanage_config()

        # Build URLs from config
        api_host = config["api"]["host"]
        api_port = config["api"]["port"]
        webui_host = config["webui"]["host"]
        webui_port = config["webui"]["port"]

        # Debug output
        print(
            f"Debug: Loaded config - API: {api_host}:{api_port}, WebUI: {webui_host}:{webui_port}"
        )

        # Resolve hosts for client connections (handle 0.0.0.0 case)
        resolved_api_host = resolve_host_for_client(api_host)
        resolved_webui_host = resolve_host_for_client(webui_host)

        self.base_url = f"http://{resolved_webui_host}:{webui_port}"
        self.api_url = f"http://{resolved_api_host}:{api_port}"
        self.timeout = 30

        print(f"Debug: Final URLs - API: {self.api_url}, WebUI: {self.base_url}")


@pytest.fixture(scope="session")
def ui_config():
    """UI test configuration"""
    return UIConfig()


def _get_browser_params():
    """Get browser parameters based on platform"""
    import platform

    # On NetBSD, only test Chrome due to Firefox WebDriver compatibility issues
    if platform.system() == "NetBSD":
        return ["chrome"]
    else:
        return ["chrome", "firefox"]


@pytest.fixture(scope="session", params=_get_browser_params())
def browser_driver(request):
    """WebDriver instance for Selenium tests - supports Chrome and Firefox (Chrome only on NetBSD)"""
    browser_name = request.param

    if browser_name == "chrome":
        driver_gen = _create_chrome_driver()
        driver = next(driver_gen)
        yield driver
        try:
            next(driver_gen)  # Trigger cleanup
        except StopIteration:
            pass
    elif browser_name == "firefox":
        driver_gen = _create_firefox_driver()
        driver = next(driver_gen)
        yield driver
        try:
            next(driver_gen)  # Trigger cleanup
        except StopIteration:
            pass
    else:
        raise ValueError(f"Unsupported browser: {browser_name}")


def _create_chrome_driver():
    """Create Chrome WebDriver instance"""
    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")

    # Set Chrome binary location based on platform
    import platform

    system = platform.system()

    chrome_binary_paths = []
    if system == "NetBSD":
        chrome_binary_paths = [
            "/usr/pkg/bin/chromium",  # NetBSD (pkgin)
            "/usr/pkg/bin/chrome",  # NetBSD alternative
        ]
    else:
        # OpenBSD, FreeBSD, Linux, etc.
        chrome_binary_paths = [
            "/usr/local/bin/chrome",  # OpenBSD/FreeBSD
            "/usr/local/bin/chromium",  # OpenBSD/FreeBSD
            "/usr/bin/google-chrome",  # Linux
            "/usr/bin/chromium-browser",  # Linux
        ]

    chrome_binary = None
    for chrome_path in chrome_binary_paths:
        if os.path.exists(chrome_path):
            chrome_binary = chrome_path
            options.binary_location = chrome_path
            break

    if not chrome_binary:
        raise RuntimeError("Chrome/Chromium binary not found")

    # Set ChromeDriver path based on platform
    chromedriver_paths = []
    if system == "NetBSD":
        chromedriver_paths = [
            "/usr/pkg/bin/chromedriver",  # NetBSD (pkgin)
        ]
    else:
        # OpenBSD, FreeBSD, Linux, etc.
        chromedriver_paths = [
            "/usr/local/bin/chromedriver",  # OpenBSD/FreeBSD
            "/usr/bin/chromedriver",  # Linux
            "/opt/chromedriver",  # Manual install
        ]

    chromedriver_path = None
    for driver_path in chromedriver_paths:
        if os.path.exists(driver_path):
            chromedriver_path = driver_path
            break

    if not chromedriver_path:
        raise RuntimeError("ChromeDriver not found")

    # Create Chrome service with explicit driver path
    service = ChromeService(executable_path=chromedriver_path)

    try:
        print(f"Using Chrome binary: {chrome_binary}")
        print(f"Using ChromeDriver: {chromedriver_path}")
        driver = webdriver.Chrome(service=service, options=options)
        yield driver
    finally:
        if "driver" in locals():
            driver.quit()


def _create_firefox_driver():
    """Create Firefox WebDriver instance"""
    options = FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")

    # Set Firefox binary location based on platform
    import platform

    system = platform.system()

    firefox_binary_paths = []
    if system == "NetBSD":
        firefox_binary_paths = [
            "/usr/pkg/bin/firefox",  # NetBSD (pkgin)
        ]
    else:
        # OpenBSD, FreeBSD, Linux, etc.
        firefox_binary_paths = [
            "/usr/local/bin/firefox",  # OpenBSD/FreeBSD
            "/usr/bin/firefox",  # Linux
            "/opt/firefox/firefox",  # Manual install
        ]

    firefox_binary = None
    for firefox_path in firefox_binary_paths:
        if os.path.exists(firefox_path):
            firefox_binary = firefox_path
            options.binary_location = firefox_path
            break

    if not firefox_binary:
        raise RuntimeError("Firefox binary not found")

    # Set GeckoDriver path based on platform
    geckodriver_paths = []
    if system == "NetBSD":
        geckodriver_paths = [
            "/usr/pkg/bin/geckodriver",  # NetBSD (pkgin)
        ]
    else:
        # OpenBSD, FreeBSD, Linux, etc.
        geckodriver_paths = [
            "/usr/local/bin/geckodriver",  # OpenBSD/FreeBSD
            "/usr/bin/geckodriver",  # Linux
            "/opt/geckodriver",  # Manual install
        ]

    geckodriver_path = None
    for driver_path in geckodriver_paths:
        if os.path.exists(driver_path):
            geckodriver_path = driver_path
            break

    if not geckodriver_path:
        raise RuntimeError("GeckoDriver not found")

    # Create Firefox service with explicit driver path
    service = FirefoxService(executable_path=geckodriver_path)

    try:
        print(f"Using Firefox binary: {firefox_binary}")
        print(f"Using GeckoDriver: {geckodriver_path}")
        driver = webdriver.Firefox(service=service, options=options)
        yield driver
    finally:
        if "driver" in locals():
            driver.quit()


# Legacy Chrome-only fixture for backward compatibility
@pytest.fixture(scope="session")
def chrome_driver():
    """Chrome WebDriver instance for Selenium tests (legacy)"""
    return _create_chrome_driver()


@pytest.fixture(scope="session")
def start_server(ui_config):
    """Ensure SysManage server is running for UI testing"""
    import requests

    print("Checking if SysManage server is already running...")

    # First, check if server is already running
    server_running = False
    try:
        response = requests.get(f"{ui_config.api_url}/api/health", timeout=5)
        if response.status_code == 200:
            server_running = True
            print(f"[OK] Server already running at {ui_config.base_url}")
    except Exception as e:
        print(f"Health check failed: {e}")
        # Also try just hitting the root endpoint
        try:
            response = requests.get(f"{ui_config.base_url}/", timeout=5)
            if response.status_code in [200, 404]:  # 404 might be OK if no root handler
                server_running = True
                print(
                    f"[OK] Server detected running at {ui_config.base_url} (via root endpoint)"
                )
        except:
            pass

    if not server_running:
        print("❌ Server not detected running on expected port.")
        print(f"   Expected: {ui_config.base_url}")
        print(
            "   Please ensure the server is running with 'make start' before running UI tests."
        )
        pytest.skip(
            f"Server not running at {ui_config.base_url} - start with 'make start' before running UI tests"
        )

    yield True

    # Never stop the server - leave it running as requested
    print("[OK] UI tests completed - leaving server running")


@pytest.fixture(scope="session")
def database_session(ui_config):
    """Create database session for test user management - use production database"""
    from backend.persistence.models.core import Base

    config = load_sysmanage_config()

    # Build database URL from config (same as production)
    db_config = config.get("database", {})
    db_user = db_config.get("user", "sysmanage")
    db_password = db_config.get("password", "")
    db_host = db_config.get("host", "localhost")
    db_port = db_config.get("port", 5432)
    db_name = db_config.get("name", "sysmanage")

    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    engine = create_engine(database_url)

    # Ensure all tables exist in the database
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture(scope="function")
def test_user(ui_config, database_session):
    """Create a test user in the production database with proper Argon2 hashing"""
    # Hash password using Argon2
    ph = PasswordHasher()
    test_password = "TestPassword123!"
    test_username = "uitest@example.com"
    test_user_id = str(uuid.uuid4())  # Generate proper UUID

    hashed_password = ph.hash(test_password)

    # Create test user data
    user_data = {
        "id": test_user_id,
        "username": test_username,
        "password": test_password,  # Plain password for login
        "hashed_password": hashed_password,
    }

    try:
        # Insert user directly into production database
        database_session.execute(
            text(
                """
                INSERT INTO "user" (id, userid, hashed_password, active, is_locked, failed_login_attempts, is_admin, created_at, updated_at)
                VALUES (:id, :userid, :hashed_password, :active, :is_locked, :failed_login_attempts, :is_admin, NOW(), NOW())
                ON CONFLICT (userid) DO UPDATE SET
                    hashed_password = EXCLUDED.hashed_password,
                    active = EXCLUDED.active,
                    is_locked = EXCLUDED.is_locked,
                    failed_login_attempts = EXCLUDED.failed_login_attempts,
                    updated_at = NOW()
                """
            ),
            {
                "id": test_user_id,
                "userid": test_username,
                "hashed_password": hashed_password,
                "active": True,
                "is_locked": False,
                "failed_login_attempts": 0,
                "is_admin": False,
            },
        )
        database_session.commit()
        print(f"Created test user: {test_username} with ID: {test_user_id}")

        yield user_data

    finally:
        # Cleanup: Delete the test user we created
        try:
            result = database_session.execute(
                text('DELETE FROM "user" WHERE userid = :userid'),
                {"userid": test_username},
            )
            database_session.commit()
            print(
                f"Deleted test user: {test_username} (affected rows: {result.rowcount})"
            )
        except Exception as e:
            print(f"Error cleaning up test user: {e}")


@pytest.fixture
def selenium_page(browser_driver, ui_config):
    """Selenium page wrapper with common functionality"""

    class SeleniumPage:
        def __init__(self, driver, config):
            self.driver = driver
            self.config = config
            self.wait = WebDriverWait(driver, config.timeout)
            self.browser_name = driver.capabilities.get("browserName", "unknown")

        def goto(self, path):
            url = f"{self.config.base_url}{path}"
            self.driver.get(url)

        def find_element(self, by, value):
            return self.wait.until(EC.presence_of_element_located((by, value)))

        def find_elements(self, by, value):
            return self.driver.find_elements(by, value)

        def wait_for_element_visible(self, by, value, timeout=None):
            if timeout:
                wait = WebDriverWait(self.driver, timeout)
            else:
                wait = self.wait
            return wait.until(EC.visibility_of_element_located((by, value)))

        def wait_for_element_clickable(self, by, value, timeout=None):
            if timeout:
                wait = WebDriverWait(self.driver, timeout)
            else:
                wait = self.wait
            return wait.until(EC.element_to_be_clickable((by, value)))

        def get_current_url(self):
            return self.driver.current_url

        def get_title(self):
            return self.driver.title

        def screenshot(self, filename):
            self.driver.save_screenshot(filename)

    return SeleniumPage(browser_driver, ui_config)
