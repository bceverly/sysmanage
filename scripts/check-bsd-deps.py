#!/usr/bin/env python3
"""
Coverage.py C tracer checker and installer.
Detects if coverage.py C tracer is unavailable and attempts to fix it.
Works on all platforms, with specific OpenBSD and NetBSD support.
"""

import platform
import subprocess
import sys
import warnings

def check_openbsd_system():
    """Check if we're running on OpenBSD."""
    return platform.system().lower() == 'openbsd'

def check_netbsd_system():
    """Check if we're running on NetBSD."""
    return platform.system().lower() == 'netbsd'

def check_bsd_system():
    """Check if we're running on any BSD system (OpenBSD or NetBSD)."""
    return check_openbsd_system() or check_netbsd_system()

def check_pkg_installed(package_name):
    """Check if a BSD package is installed (works on both OpenBSD and NetBSD)."""
    try:
        result = subprocess.run(['pkg_info', '-e', package_name],
                              capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def check_c_tracer_available():
    """Check if coverage C tracer is available using coverage debug command."""
    try:
        result = subprocess.run([
            sys.executable, '-m', 'coverage', 'debug', 'sys'
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            output = result.stdout.lower()

            # Check for CTracer status in debug output
            if 'ctracer:' in output:
                if 'available' in output and 'unavailable' not in output:
                    print("[OK] Coverage C tracer is available and active")
                    return True
                elif 'unavailable' in output:
                    print("[WARN]  Coverage C tracer is unavailable - needs reinstallation")
                    return False

            # Fallback: try direct import
            try:
                import coverage.tracer
                print("[OK] Coverage C tracer is available (verified by import)")
                return True
            except ImportError:
                print("[WARN]  Coverage C tracer not available - using Python tracer (slower)")
                return False
        else:
            print("[WARN]  Could not check C tracer status via coverage debug")
            return False

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        print(f"[WARN]  Error checking C tracer status: {e}")
        # Fallback to import test
        try:
            import coverage.tracer
            print("[OK] Coverage C tracer available (fallback check)")
            return True
        except ImportError:
            print("[WARN]  Coverage C tracer not available (fallback check)")
            return False

def install_coverage_with_c_extension():
    """Reinstall coverage with C extension on OpenBSD."""
    try:
        print("[SETUP] Reinstalling coverage with C extension...")

        # Uninstall existing coverage
        subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'coverage'],
                      check=False, capture_output=True)

        # Reinstall with forced compilation
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install',
            '--force-reinstall', '--no-binary=:all:', 'coverage'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("[OK] Coverage reinstalled with C extension")
            return True
        else:
            print(f"[ERROR] Failed to reinstall coverage: {result.stderr}")
            return False

    except Exception as e:
        print(f"[ERROR] Error reinstalling coverage: {e}")
        return False

def verify_c_tracer():
    """Verify C tracer is working after installation."""
    try:
        result = subprocess.run([
            sys.executable, '-m', 'coverage', 'debug', 'sys'
        ], capture_output=True, text=True)

        if 'CTracer' in result.stdout:
            print("[OK] C tracer is active and working")
            return True
        else:
            print("[WARN]  C tracer not active, using Python tracer")
            return False

    except Exception as e:
        print(f"[ERROR] Error checking tracer status: {e}")
        return False

def main():
    print("Coverage.py C Tracer Dependency Check")
    print("=" * 40)

    system_name = platform.system()
    print(f"[INFO] Detected {system_name} system")

    # Check C tracer status first (applies to all platforms)
    if check_c_tracer_available():
        print("[OK] C tracer already working - no action needed")
        return

    print("[SETUP] C tracer not available - checking dependencies...")

    # BSD-specific package checks (OpenBSD and NetBSD)
    if check_bsd_system():
        # Check if development tools are available
        if check_openbsd_system():
            required_packages = [
                'gcc',  # C compiler
                'py3-cffi',  # Python CFFI for C extensions
            ]
        elif check_netbsd_system():
            required_packages = [
                'gcc13',  # C compiler (NetBSD typically uses versioned gcc packages)
                'py312-cffi',  # Python CFFI for C extensions (Python 3.12)
            ]

        missing_packages = []
        for package in required_packages:
            if not check_pkg_installed(package):
                missing_packages.append(package)

        if missing_packages:
            print("[WARN]  Missing required packages for C extension compilation:")
            for pkg in missing_packages:
                print(f"   - {pkg}")
            print()
            print("To install missing packages:")
            if check_openbsd_system():
                print(f"   doas pkg_add {' '.join(missing_packages)}")
            elif check_netbsd_system():
                print(f"   pkgin install {' '.join(missing_packages)}")
                print("   # or using pkg_add:")
                print(f"   pkg_add {' '.join(missing_packages)}")
            print()
            print("Note: C tracer will use Python fallback (slower but functional)")
            return

        print("[OK] Required compilation tools are available")
    else:
        # Non-BSD systems - assume dev tools are available or user can install them
        print("ℹ️  Non-BSD system - assuming development tools are available")

    # Try to reinstall coverage with C extension (works on all platforms)
    print("[SETUP] Attempting to reinstall coverage with C extension...")

    if install_coverage_with_c_extension():
        # Verify it worked
        if verify_c_tracer():
            print("\n🎉 C tracer successfully enabled!")
            print("Coverage.py will now run at native speed")
        else:
            print("\n[WARN]  C tracer installation completed but not active")
            print("Coverage will work but use slower Python implementation")
    else:
        print("\n[WARN]  Could not install C tracer - using Python fallback")
        print("Coverage will work but run slower")
        if not check_bsd_system():
            print("You may need to install development tools (gcc, python-dev, etc.)")

    print("\nNote: This only affects test coverage speed, not functionality")

if __name__ == "__main__":
    # Suppress coverage warnings during this check
    warnings.filterwarnings('ignore', message='Couldn\'t import C tracer')
    main()