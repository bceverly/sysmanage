#!/usr/bin/env python3
"""
Post-install script to install WebDriver for browser automation.
Run this after: pip install -r requirements.txt
"""

import subprocess
import sys
import os
import warnings

# Suppress urllib3 LibreSSL warning on OpenBSD
warnings.filterwarnings('ignore', message='urllib3 v2 only supports OpenSSL')

def install_webdriver():
    """Install Chrome WebDriver for screenshot capabilities."""
    import platform
    system = platform.system().lower()

    # Check if we're on BSD systems - skip automatic driver download
    if system in ['openbsd', 'freebsd', 'netbsd']:
        print("Detected BSD system - using system browser directly...")
        return detect_system_browser()

    try:
        print("Setting up Chrome WebDriver...")

        # Try to set up ChromeDriver automatically
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()
        print(f"[OK] ChromeDriver installed at: {driver_path}")
        return True

    except ImportError:
        print("[ERROR] webdriver-manager not found. Make sure you've installed requirements.txt first")
        return False
    except Exception as e:
        print(f"[WARN]  ChromeDriver setup failed: {e}")
        print("Falling back to system browser detection...")
        return detect_system_browser()

def detect_system_browser():
    """Detect available system browsers."""
    import platform
    system = platform.system().lower()

    # Check if chromium or chrome is available in system
    browsers = ['chromium', 'chromium-browser', 'google-chrome', 'chrome']
    if system == 'windows':
        # On Windows, use 'where' instead of 'which'
        command = 'where'
    else:
        command = 'which'

    for browser in browsers:
        try:
            result = subprocess.run([command, browser], capture_output=True)
            if result.returncode == 0:
                browser_path = result.stdout.decode().strip()
                print(f"[OK] Found system browser: {browser_path}")
                return True
        except:
            continue

    print("[ERROR] No suitable browser found")
    print("Please install a browser:")
    print("  - On OpenBSD: pkg_add chromium")
    print("  - On FreeBSD: pkg install chromium")
    print("  - On NetBSD: pkgin install chromium")
    print("  - On Linux: apt-get install chromium-browser")
    print("  - On macOS: brew install --cask google-chrome")
    return False

def install_playwright_browsers():
    """Install Playwright browsers."""
    import platform
    system = platform.system().lower()

    # Check if we're on OpenBSD or FreeBSD - skip Playwright
    if system in ['openbsd', 'freebsd']:
        print("Detected BSD system - Playwright not supported, using Selenium fallback")
        return True

    try:
        print("Installing Playwright browsers...")

        # Check if playwright is installed
        import playwright
        try:
            version = getattr(playwright, '__version__', 'unknown')
        except AttributeError:
            version = 'unknown'
        print(f"[OK] Playwright {version} found")

        # Install all browsers for all platforms
        browsers_to_install = ["chromium", "firefox"]

        # Add webkit only on macOS
        if system == "darwin":
            browsers_to_install.append("webkit")
            print("[INFO] macOS detected - including WebKit/Safari support")

        for browser in browsers_to_install:
            print(f"Installing {browser}...")
            result = subprocess.run([
                sys.executable, "-m", "playwright", "install", browser
            ], capture_output=True, text=True)

            if result.returncode == 0:
                print(f"[OK] {browser} installed successfully")
            else:
                print(f"[WARN] Failed to install {browser}: {result.stderr}")
                return False

        # Install system dependencies
        print("Installing Playwright system dependencies...")
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install-deps"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("[OK] Playwright system dependencies installed")
        else:
            print(f"[WARN] Failed to install system dependencies: {result.stderr}")
            # Don't fail here as this might work anyway

        return True

    except ImportError:
        print("[INFO] Playwright not found, skipping browser installation")
        return True
    except Exception as e:
        print(f"[WARN] Playwright browser installation failed: {e}")
        return False

def main():
    print("SysManage WebDriver Installation")
    print("=" * 40)

    # Check if selenium is installed
    try:
        import selenium
        print(f"[OK] Selenium {selenium.__version__} found")
    except ImportError:
        print("[ERROR] Selenium not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    # Install WebDriver
    webdriver_success = install_webdriver()

    # Install Playwright browsers
    playwright_success = install_playwright_browsers()

    if webdriver_success and playwright_success:
        print("\n[SUCCESS] WebDriver setup complete!")
        print("You can now use screenshot capabilities in SysManage")
    elif webdriver_success:
        print("\n[PARTIAL] WebDriver setup complete, but Playwright installation had issues")
        print("Selenium-based features will work, but Playwright tests may not")
    else:
        print("\n[WARN]  WebDriver setup failed")
        print("Screenshot capabilities may not work properly")
        print("You may need to install Chrome/Chromium manually:")
        print("  - On OpenBSD: pkg_add chromium")
        print("  - On FreeBSD: pkg install chromium")
        print("  - On NetBSD: pkgin install chromium")
        print("  - On Linux: apt-get install chromium-browser")
        print("  - On macOS: brew install --cask google-chrome")
        sys.exit(1)

if __name__ == "__main__":
    main()