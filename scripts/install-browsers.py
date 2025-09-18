#!/usr/bin/env python3
"""
Post-install script to install Playwright browsers.
Run this after: pip install -r requirements.txt
"""

import subprocess
import sys
import os

def install_playwright_browsers():
    """Install Playwright Chromium browser for screenshot capabilities."""
    try:
        print("Installing Playwright Chromium browser...")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Chromium browser installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Chromium browser: {e}")
        print("Error output:", e.stderr)
        return False
    except FileNotFoundError:
        print("❌ Playwright not found. Make sure you've installed requirements.txt first")
        return False

def main():
    print("SysManage Browser Installation")
    print("=" * 40)

    # Check if playwright is installed
    try:
        import playwright
        print(f"✅ Playwright {playwright.__version__} found")
    except ImportError:
        print("❌ Playwright not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    # Install browsers
    success = install_playwright_browsers()

    if success:
        print("\n🎉 Browser installation complete!")
        print("You can now use screenshot capabilities in SysManage")
    else:
        print("\n⚠️  Browser installation failed")
        print("Screenshot capabilities may not work properly")
        sys.exit(1)

if __name__ == "__main__":
    main()