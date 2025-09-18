#!/usr/bin/env python3
"""
Post-install script to install WebDriver for browser automation.
Run this after: pip install -r requirements.txt
"""

import subprocess
import sys
import os

def install_webdriver():
    """Install Chrome WebDriver for screenshot capabilities."""
    import platform
    system = platform.system().lower()

    # Check if we're on OpenBSD or FreeBSD - skip automatic driver download
    if system in ['openbsd', 'freebsd']:
        print("Detected BSD system - using system browser directly...")
        return detect_system_browser()

    try:
        print("Setting up Chrome WebDriver...")

        # Try to set up ChromeDriver automatically
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()
        print(f"✅ ChromeDriver installed at: {driver_path}")
        return True

    except ImportError:
        print("❌ webdriver-manager not found. Make sure you've installed requirements.txt first")
        return False
    except Exception as e:
        print(f"⚠️  ChromeDriver setup failed: {e}")
        print("Falling back to system browser detection...")
        return detect_system_browser()

def detect_system_browser():
    """Detect available system browsers."""
    # Check if chromium or chrome is available in system
    browsers = ['chromium', 'chromium-browser', 'google-chrome', 'chrome']
    for browser in browsers:
        try:
            result = subprocess.run(['which', browser], capture_output=True)
            if result.returncode == 0:
                browser_path = result.stdout.decode().strip()
                print(f"✅ Found system browser: {browser_path}")
                return True
        except:
            continue

    print("❌ No suitable browser found")
    print("Please install a browser:")
    print("  - On OpenBSD: pkg_add chromium")
    print("  - On FreeBSD: pkg install chromium")
    print("  - On Linux: apt-get install chromium-browser")
    print("  - On macOS: brew install --cask google-chrome")
    return False

def main():
    print("SysManage WebDriver Installation")
    print("=" * 40)

    # Check if selenium is installed
    try:
        import selenium
        print(f"✅ Selenium {selenium.__version__} found")
    except ImportError:
        print("❌ Selenium not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    # Install WebDriver
    success = install_webdriver()

    if success:
        print("\n🎉 WebDriver setup complete!")
        print("You can now use screenshot capabilities in SysManage")
    else:
        print("\n⚠️  WebDriver setup failed")
        print("Screenshot capabilities may not work properly")
        print("You may need to install Chrome/Chromium manually:")
        print("  - On OpenBSD: pkg_add chromium")
        print("  - On Linux: apt-get install chromium-browser")
        print("  - On macOS: brew install --cask google-chrome")
        sys.exit(1)

if __name__ == "__main__":
    main()