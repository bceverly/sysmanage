"""
UI Test Configuration and Fixtures
Provides test fixtures for Playwright-based UI testing with proper cleanup
"""

import asyncio
import os
import signal
import subprocess
import time
import uuid
from typing import Generator, Optional

import pytest
import yaml
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.persistence.models.core import User


def cleanup_leftover_test_users():
    """Utility function to clean up any leftover test users"""
    config = UITestConfig()
    engine = create_engine(config.get_database_url())
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        result = session.execute(
            text('DELETE FROM "user" WHERE userid LIKE :pattern'),
            {"pattern": "%ui_test_user_%"},
        )
        session.commit()
        count = result.rowcount
        if count > 0:
            print(f"Cleaned up {count} leftover test users")
        return count
    except Exception as e:
        print(f"Warning: Failed to clean up leftover test users: {e}")
        session.rollback()
        return 0
    finally:
        session.close()


class UITestConfig:
    """Configuration for UI tests"""

    def __init__(self):
        self.test_user_id = str(uuid.uuid4())
        self.test_username = f"ui_test_user_{int(time.time())}@example.com"
        self.test_password = "TestPassword123!"
        self.server_process: Optional[subprocess.Popen] = None
        self.base_url = "http://localhost:3000"

    def get_database_url(self) -> str:
        """Get database URL - use production database for UI tests"""
        # Use production database since the running backend connects to it
        return "postgresql://sysmanage:abc123@localhost:5432/sysmanage"

    def get_salt(self) -> str:
        """Get salt from production configuration"""
        # Use production password salt from /etc/sysmanage.yaml
        return "b3a5a4c28062b69a9e2757667f3023cf261a1befd6d3800b46b30dadcb833d3c"


@pytest.fixture(scope="session")
def ui_config() -> Generator[UITestConfig, None, None]:
    """Provide UI test configuration"""
    config = UITestConfig()
    yield config


@pytest.fixture(scope="session")
def start_server(ui_config: UITestConfig) -> Generator[bool, None, None]:
    """Ensure SysManage server is running for UI testing"""
    print("Checking if SysManage server is already running...")

    # First, check if server is already running
    server_running = False
    try:
        import requests

        response = requests.get("http://localhost:8080/api/health", timeout=5)
        if response.status_code == 200:
            server_running = True
            print(f"✓ Server already running at {ui_config.base_url}")
    except Exception as e:
        print(f"Health check failed: {e}")
        # Also try just hitting the root endpoint
        try:
            response = requests.get(f"{ui_config.base_url}/", timeout=5)
            if response.status_code in [200, 404]:  # 404 might be OK if no root handler
                server_running = True
                print(
                    f"✓ Server detected running at {ui_config.base_url} (via root endpoint)"
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
    print("✓ UI tests completed - leaving server running")


@pytest.fixture(scope="session")
def database_session(ui_config: UITestConfig):
    """Create database session for test user management - reuse existing test DB"""
    from backend.persistence.models.core import Base

    engine = create_engine(ui_config.get_database_url())

    # Ensure all tables exist in the test database
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture(scope="function")
def test_user(ui_config: UITestConfig, database_session) -> Generator[dict, None, None]:
    """Create a test user in the database with proper Argon2 hashing"""
    # Hash password using Argon2 (no additional salt needed)
    ph = PasswordHasher()
    hashed_password = ph.hash(ui_config.test_password)

    # Create test user
    user_data = {
        "id": ui_config.test_user_id,
        "username": ui_config.test_username,
        "password": ui_config.test_password,  # Plain password for login
        "hashed_password": hashed_password,
    }

    try:
        # Insert user directly into database
        database_session.execute(
            text(
                """
                INSERT INTO "user" (id, userid, hashed_password, active, is_locked, failed_login_attempts, is_admin, created_at, updated_at)
                VALUES (:id, :userid, :hashed_password, :active, :is_locked, :failed_login_attempts, :is_admin, NOW(), NOW())
            """
            ),
            {
                "id": ui_config.test_user_id,
                "userid": ui_config.test_username,
                "hashed_password": hashed_password,
                "active": True,
                "is_locked": False,
                "failed_login_attempts": 0,
                "is_admin": False,
            },
        )
        database_session.commit()
        print(f"Created test user: {ui_config.test_username}")

        yield user_data

    finally:
        # Cleanup: Delete ONLY the test user we created
        try:
            result = database_session.execute(
                text('DELETE FROM "user" WHERE userid = :userid'),
                {"userid": ui_config.test_username},
            )
            database_session.commit()
            print(
                f"Deleted test user: {ui_config.test_username} (affected rows: {result.rowcount})"
            )
        except Exception as e:
            print(f"Warning: Failed to delete test user {ui_config.test_username}: {e}")
            database_session.rollback()


@pytest.fixture(scope="function")
async def playwright_instance():
    """Provide Playwright instance with fallback handling"""
    try:
        async with async_playwright() as p:
            yield p
    except Exception as e:
        pytest.skip(
            f"Playwright not available: {e}. Install system dependencies with 'sudo playwright install-deps'"
        )


@pytest.fixture(scope="function")
async def browser_context(
    playwright_instance, request
) -> Generator[BrowserContext, None, None]:
    """Create browser context for each test"""
    # Get browser type from test marker or default to chromium
    browser_name = getattr(request, "param", "chromium")

    # Launch browser in headless mode (works on servers without display)
    launch_options = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],  # Common headless server options
    }

    if browser_name == "chromium":
        browser = await playwright_instance.chromium.launch(**launch_options)
    elif browser_name == "firefox":
        browser = await playwright_instance.firefox.launch(
            headless=True
        )  # Firefox doesn't need the extra args
    elif browser_name == "webkit":
        browser = await playwright_instance.webkit.launch(headless=True)
    else:
        raise ValueError(f"Unsupported browser: {browser_name}")

    context = await browser.new_context(
        viewport={"width": 1280, "height": 720}, ignore_https_errors=True
    )

    yield context

    await context.close()
    await browser.close()


@pytest.fixture(scope="function")
async def page(browser_context: BrowserContext) -> Generator[Page, None, None]:
    """Create a new page for each test"""
    page = await browser_context.new_page()
    yield page
    await page.close()


# Browser type markers for parametrized tests
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line("markers", "chromium: mark test to run on Chromium browser")
    config.addinivalue_line("markers", "firefox: mark test to run on Firefox browser")
    config.addinivalue_line(
        "markers", "webkit: mark test to run on WebKit browser (Safari)"
    )
