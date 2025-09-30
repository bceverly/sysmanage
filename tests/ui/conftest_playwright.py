"""
UI Test Configuration and Fixtures for Playwright
Provides test fixtures for Playwright-based UI testing with proper cleanup
Supports Chrome, Firefox, and WebKit/Safari (macOS only)
"""

import asyncio
import os
import signal
import subprocess
import time
import uuid
import platform
from typing import Generator, Optional

import pytest
import yaml
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
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

    server_process = None
    if not server_running:
        print("❌ Server not detected running on expected port.")
        print(f"   Starting server at {ui_config.base_url}")

        # Start the server using run.sh
        try:
            # Change to project root directory
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../..")
            )
            print(f"   Project root: {project_root}")

            # Start server in background using scripts/start.sh
            run_script = os.path.join(project_root, "scripts", "start.sh")
            if not os.path.exists(run_script):
                raise FileNotFoundError(f"start.sh not found at {run_script}")

            server_process = subprocess.Popen(
                [run_script],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if os.name != "nt" else None,
            )

            print(f"   Server process started (PID: {server_process.pid})")
            print("   Waiting for server to be ready...")

            # Wait up to 60 seconds for server to be ready
            max_wait = 60
            wait_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval

                try:
                    response = requests.get(
                        f"{ui_config.api_url}/api/health", timeout=5
                    )
                    if response.status_code == 200:
                        print(f"   [OK] Server ready after {elapsed} seconds")
                        server_running = True
                        break
                except:
                    # Try root endpoint as fallback
                    try:
                        response = requests.get(f"{ui_config.base_url}/", timeout=5)
                        if response.status_code in [200, 404]:
                            print(
                                f"   [OK] Server ready after {elapsed} seconds (via root endpoint)"
                            )
                            server_running = True
                            break
                    except:
                        pass

                print(f"   Waiting... ({elapsed}/{max_wait}s)")

            if not server_running:
                # Clean up failed server process
                if server_process:
                    (
                        os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
                        if os.name != "nt"
                        else server_process.terminate()
                    )
                raise Exception(f"Server failed to start within {max_wait} seconds")

        except Exception as e:
            print(f"   [ERROR] Failed to start server: {e}")
            if server_process:
                try:
                    (
                        os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
                        if os.name != "nt"
                        else server_process.terminate()
                    )
                except:
                    pass
            raise

    yield True

    # Clean up: stop the server if we started it
    if server_process:
        print("[INFO] Stopping server that was started for UI tests")
        try:
            # Use scripts/stop.sh to cleanly stop the server
            # Redirect all output including shell job control messages
            project_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../..")
            )
            stop_script = os.path.join(project_root, "scripts", "stop.sh")
            if os.path.exists(stop_script):
                # Run stop script in a subshell to completely suppress output
                result = subprocess.run(
                    ["sh", "-c", f"'{stop_script}' >/dev/null 2>&1"],
                    cwd=project_root,
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print("[OK] Server stopped successfully using stop.sh")
            else:
                # Fallback to signal-based termination
                if os.name != "nt":
                    os.killpg(os.getpgid(server_process.pid), signal.SIGTERM)
                else:
                    server_process.terminate()
                server_process.wait(timeout=10)
                print("[OK] Server stopped successfully")
        except Exception as e:
            print(f"[WARNING] Error stopping server: {e}")
    else:
        print("[OK] UI tests completed - leaving pre-existing server running")


@pytest.fixture(scope="session")
def database_session(ui_config):
    """Create database session for test user management - use production database"""
    from backend.persistence.models.core import Base
    from backend.persistence.db import get_database_url

    # Use the same database URL logic as the main backend, but force PostgreSQL in CI
    import os

    database_url = os.getenv("DATABASE_URL") or get_database_url()
    # Redact password from database URL for logging
    import re

    safe_url = re.sub(r":([^:@]+)@", ":***@", database_url)
    print(f"UI tests using database URL: {safe_url}")

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
    test_username = f"uitest_{int(time.time())}@example.com"
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
        # Use database-agnostic timestamp handling
        from datetime import datetime

        current_time = datetime.utcnow()

        # Insert user directly into production database
        database_session.execute(
            text(
                """
                INSERT INTO "user" (id, userid, hashed_password, active, is_locked, failed_login_attempts, is_admin, created_at, updated_at)
                VALUES (:id, :userid, :hashed_password, :active, :is_locked, :failed_login_attempts, :is_admin, :created_at, :updated_at)
                ON CONFLICT (userid) DO UPDATE SET
                    hashed_password = EXCLUDED.hashed_password,
                    active = EXCLUDED.active,
                    is_locked = EXCLUDED.is_locked,
                    failed_login_attempts = EXCLUDED.failed_login_attempts,
                    updated_at = :updated_at
                """
            ),
            {
                "id": test_user_id,
                "userid": test_username,
                "hashed_password": hashed_password,
                "active": True,
                "is_locked": False,
                "failed_login_attempts": 0,
                "is_admin": True,
                "created_at": current_time,
                "updated_at": current_time,
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


@pytest.fixture(scope="function")
async def playwright_instance():
    """Provide Playwright instance with fallback handling"""
    try:
        async with async_playwright() as p:
            yield p
    except Exception as e:
        pytest.skip(
            f"Playwright not available: {e}. Install browsers with 'python -m playwright install'"
        )


@pytest.fixture(scope="function")
async def browser_context(
    playwright_instance, request
) -> Generator[BrowserContext, None, None]:
    """Create browser context for each test - supports chromium, firefox, and webkit (macOS only)"""
    # Get browser type from test marker or default to chromium
    browser_name = getattr(request, "param", "chromium")

    # Skip webkit on non-macOS systems
    if browser_name == "webkit" and platform.system() != "Darwin":
        pytest.skip("WebKit/Safari tests only run on macOS")

    # Launch browser in headless mode (works on servers without display)
    # Add memory optimization flags to reduce OOM risk
    launch_options = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            "--no-first-run",
        ],
    }

    if browser_name == "chromium":
        browser = await playwright_instance.chromium.launch(**launch_options)
    elif browser_name == "firefox":
        # Firefox with memory optimization
        browser = await playwright_instance.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "browser.cache.disk.enable": False,
                "browser.cache.memory.enable": False,
            },
        )
    elif browser_name == "webkit":
        browser = await playwright_instance.webkit.launch(headless=True)
    else:
        raise ValueError(f"Unsupported browser: {browser_name}")

    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        java_script_enabled=True,  # Explicitly enable JavaScript
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
        "markers", "webkit: mark test to run on WebKit browser (Safari) - macOS only"
    )
