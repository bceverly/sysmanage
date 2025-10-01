#!/usr/bin/env python3
"""
OpenBAO installation script for sysmanage development environment.
Automatically detects platform and installs OpenBAO accordingly.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

import requests


def safe_extract(tar, path):
    """Safely extract tar file, preventing path traversal attacks."""
    def is_within_directory(directory, target):
        abs_directory = os.path.abspath(directory)
        abs_target = os.path.abspath(target)
        prefix = os.path.commonpath([abs_directory, abs_target])
        return prefix == abs_directory

    def safe_members(tar):
        for member in tar.getmembers():
            if is_within_directory(path, os.path.join(path, member.name)):
                yield member

    tar.extractall(path, members=safe_members(tar))


def detect_platform():
    """Detect the current platform and return appropriate OpenBAO binary info."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map Python's machine names to OpenBAO's naming convention
    if machine in ['x86_64', 'amd64']:
        arch = 'amd64'
    elif machine in ['aarch64', 'arm64']:
        arch = 'arm64'
    elif machine in ['armv7l', 'armv6l']:
        arch = 'arm'
    else:
        arch = machine

    if system == 'linux':
        return f'linux_{arch}'
    elif system == 'darwin':
        return f'darwin_{arch}'
    elif system == 'windows':
        return f'windows_{arch}'
    elif system == 'freebsd':
        return f'freebsd_{arch}'
    elif system == 'openbsd':
        return f'openbsd_{arch}'
    elif system == 'netbsd':
        return f'netbsd_{arch}'
    else:
        raise ValueError(f"Unsupported platform: {system}_{arch}")


def check_openbao_installed():
    """Check if OpenBAO is already installed and accessible."""
    # Check if 'bao' is in PATH
    try:
        result = subprocess.run(['bao', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"OpenBAO already installed: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass

    # Check common installation locations based on platform
    system = platform.system().lower()
    binary_name = 'bao.exe' if system == 'windows' else 'bao'

    if system == 'windows':
        # Windows-specific paths to check
        potential_paths = [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "bin", binary_name),
            os.path.join(os.path.expanduser("~"), "bin", binary_name),
            os.path.join("C:", "Program Files", "OpenBAO", binary_name),
            os.path.join("C:", "Program Files (x86)", "OpenBAO", binary_name),
        ]
    else:
        # Unix-like systems
        potential_paths = [
            os.path.join(os.path.expanduser("~"), '.local', 'bin', binary_name),
            os.path.join('/usr', 'local', 'bin', binary_name),
            os.path.join('/opt', 'openbao', 'bin', binary_name),
        ]

    for path in potential_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            try:
                result = subprocess.run([path, 'version'], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"OpenBAO already installed at {path}: {result.stdout.strip()}")
                    # Add to PATH hint if not already accessible
                    if system == 'windows':
                        parent_dir = os.path.dirname(path)
                        print(f"Note: Add {parent_dir} to your PATH to use 'bao' command globally")
                    return True
            except Exception:
                continue

    return False


def check_openbao_at_path(install_path):
    """Check if OpenBAO is installed at a specific path."""
    binary_name = 'bao.exe' if platform.system().lower() == 'windows' else 'bao'
    binary_path = os.path.join(install_path, binary_name)

    if os.path.exists(binary_path):
        try:
            result = subprocess.run([binary_path, 'version'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"OpenBAO installed at {binary_path}: {result.stdout.strip()}")
                return True
        except:
            pass
    return False


def install_via_package_manager():
    """Try to install OpenBAO via platform-specific package managers."""
    system = platform.system().lower()

    try:
        if system == 'darwin':
            # Try Homebrew on macOS
            print("Attempting to install OpenBAO via Homebrew...")
            result = subprocess.run(['brew', 'install', 'openbao'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("OpenBAO installed successfully via Homebrew!")
                return True
            else:
                print(f"Homebrew installation failed: {result.stderr}")

        elif system == 'freebsd':
            # Try pkg on FreeBSD
            print("Attempting to install OpenBAO via pkg...")
            result = subprocess.run(['sudo', 'pkg', 'install', '-y', 'openbao'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("OpenBAO installed successfully via pkg!")
                return True
            else:
                print(f"pkg installation failed: {result.stderr}")

        elif system == 'netbsd':
            print("NetBSD detected - checking for existing installations...")

            # Check if OpenBAO is already installed manually
            if shutil.which('bao'):
                print("OpenBAO (bao) found in PATH!")
                return True

            # Check if we have a previously built binary in the project
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(script_dir)
            built_binary = os.path.join(project_dir, '.build', 'openbao', 'bin', 'bao')

            if os.path.exists(built_binary):
                print(f"Found previously built OpenBAO binary: {built_binary}")
                try:
                    # Test if the binary works
                    result = subprocess.run([built_binary, 'version'],
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("Previous build is working! Installing to local bin...")
                        # Install to user's local bin
                        install_path = os.path.expanduser("~/.local/bin")
                        os.makedirs(install_path, exist_ok=True)
                        target_path = os.path.join(install_path, 'bao')
                        shutil.copy2(built_binary, target_path)
                        os.chmod(target_path, 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                        print(f"OpenBAO installed to: {target_path}")
                        print("Add ~/.local/bin to your PATH if not already done")
                        return True
                    else:
                        print("Previous build exists but doesn't work properly")
                        print("Will offer to rebuild...")
                except Exception as e:
                    print(f"Previous build exists but failed to test: {e}")
                    print("Will offer to rebuild...")

            # Check if vault is already installed
            if shutil.which('vault'):
                print("HashiCorp Vault found in PATH!")
                print("Note: You can use 'vault' instead of 'bao' for development")
                # Try to create symlink for compatibility if we have privileges
                try:
                    subprocess.run(['sudo', 'ln', '-sf', '/usr/pkg/bin/vault', '/usr/pkg/bin/bao'],
                                 capture_output=True, text=True, check=False)
                    print("Created 'bao' symlink to vault for compatibility")
                except:
                    pass
                return True

            # NetBSD doesn't have OpenBAO in packages - offer to build from source
            print("OpenBAO is not available in NetBSD packages.")
            print("Would you like to build OpenBAO from source? This requires Go and Git.")
            print("(This will take 5-10 minutes depending on your system)")
            print("")

            # Check for required dependencies first
            if not shutil.which('go'):
                print("Go is required to build OpenBAO from source.")
                print("")
                print("Install Go with:")
                print("  pkgin install go")
                print("")
                print("Then re-run: gmake install-dev")
                print("")
                print("Note: OpenBAO is optional - the system works without it (vault.enabled=false)")
                return False

            if not shutil.which('git'):
                print("Git is required to download OpenBAO source.")
                print("")
                print("Install Git with:")
                print("  pkgin install git")
                print("")
                print("Then re-run: gmake install-dev")
                print("")
                print("Note: OpenBAO is optional - the system works without it (vault.enabled=false)")
                return False

            if not shutil.which('gmake'):
                print("GNU make is required to build OpenBAO from source.")
                print("")
                print("Install GNU make with:")
                print("  pkgin install gmake")
                print("")
                print("Then re-run: gmake install-dev")
                print("")
                print("Note: OpenBAO is optional - the system works without it (vault.enabled=false)")
                return False

            try:
                response = input("Build OpenBAO from source? [y/N]: ").strip().lower()
                if response in ['y', 'yes']:
                    print("Building OpenBAO from source...")

                    # Run the build script
                    build_script = os.path.join(os.path.dirname(__file__), 'build-openbao.sh')
                    result = subprocess.run(['sh', build_script],
                                          capture_output=False, text=True)

                    if result.returncode == 0:
                        print("OpenBAO built and installed successfully!")
                        return True
                    else:
                        print("Build failed. You can try building manually or use vault.enabled=false")
                        return False
                else:
                    print("Skipping OpenBAO build.")
                    print("The development environment will work fine with vault.enabled=false")
                    return False
            except (KeyboardInterrupt, EOFError):
                print("\nSkipping OpenBAO build.")
                print("The development environment will work fine with vault.enabled=false")
                return False

        elif system == 'openbsd':
            print("OpenBSD detected - checking for existing installations...")

            # Check if OpenBAO is already installed manually
            if shutil.which('bao'):
                print("OpenBAO (bao) found in PATH!")
                return True

            # Check if we have a previously built binary in the project
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(script_dir)
            built_binary = os.path.join(project_dir, '.build', 'openbao', 'bin', 'bao')

            if os.path.exists(built_binary):
                print(f"Found previously built OpenBAO binary: {built_binary}")
                try:
                    # Test if the binary works
                    result = subprocess.run([built_binary, 'version'],
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("Previous build is working! Installing to local bin...")
                        # Install to user's local bin
                        install_path = os.path.expanduser("~/.local/bin")
                        os.makedirs(install_path, exist_ok=True)
                        target_path = os.path.join(install_path, 'bao')
                        shutil.copy2(built_binary, target_path)
                        os.chmod(target_path, 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                        print(f"OpenBAO installed to: {target_path}")
                        print("Add ~/.local/bin to your PATH if not already done")
                        return True
                    else:
                        print("Previous build exists but doesn't work properly")
                        print("Will offer to rebuild...")
                except Exception as e:
                    print(f"Previous build exists but failed to test: {e}")
                    print("Will offer to rebuild...")

            # Check if vault is already installed
            if shutil.which('vault'):
                print("HashiCorp Vault found in PATH!")
                print("Note: You can use 'vault' instead of 'bao' for development")
                # Try to create symlink for compatibility if we have privileges
                if shutil.which('doas'):
                    try:
                        subprocess.run(['doas', 'ln', '-sf', '/usr/local/bin/vault', '/usr/local/bin/bao'],
                                     capture_output=True, text=True, check=False)
                        print("Created 'bao' symlink to vault for compatibility")
                    except:
                        pass
                return True

            # OpenBSD doesn't have OpenBAO in packages - offer to build from source
            print("OpenBAO is not available in OpenBSD packages.")
            print("Would you like to build OpenBAO from source? This requires Go and Git.")
            print("(This will take 5-10 minutes depending on your system)")
            print("")

            # Check for required dependencies first
            if not shutil.which('go'):
                print("Go is required to build OpenBAO from source.")
                print("")
                print("Install Go with:")
                print("  doas pkg_add go")
                print("")
                print("Then re-run: make install-dev")
                return False

            # Check Go version and warn if potentially incompatible
            try:
                result = subprocess.run(['go', 'version'], capture_output=True, text=True)
                if result.returncode == 0:
                    version_output = result.stdout.strip()
                    # Extract version number (e.g., "go version go1.24.1 openbsd/amd64" -> "1.24.1")
                    import re
                    version_match = re.search(r'go(\d+\.\d+\.\d+)', version_output)
                    if version_match:
                        current_version = version_match.group(1)
                        print(f"Found Go version: {current_version}")

                        # Check if version is at least 1.24.6
                        version_parts = [int(x) for x in current_version.split('.')]
                        required_parts = [1, 24, 6]

                        if (version_parts[0] < required_parts[0] or
                            (version_parts[0] == required_parts[0] and version_parts[1] < required_parts[1]) or
                            (version_parts[0] == required_parts[0] and version_parts[1] == required_parts[1] and version_parts[2] < required_parts[2])):
                            print(f"Note: Latest OpenBAO prefers Go 1.24.6+, but trying with {current_version}")
                            print("Will attempt to build an older compatible version...")
            except Exception as e:
                print(f"Could not check Go version: {e}")
                print("Continuing with build attempt...")

            if not shutil.which('git'):
                print("Git is required to download OpenBAO source.")
                print("")
                print("Install Git with:")
                print("  doas pkg_add git")
                print("")
                print("Then re-run: make install-dev")
                return False

            if not shutil.which('gmake'):
                print("GNU make is required to build OpenBAO from source.")
                print("")
                print("Install GNU make with:")
                print("  doas pkg_add gmake")
                print("")
                print("Then re-run: make install-dev")
                return False

            try:
                response = input("Build OpenBAO from source? [y/N]: ").strip().lower()
                if response in ['y', 'yes']:
                    print("Building OpenBAO from source...")

                    # Run the build script
                    build_script = os.path.join(os.path.dirname(__file__), 'build-openbao.sh')
                    result = subprocess.run(['sh', build_script],
                                          capture_output=False, text=True)

                    if result.returncode == 0:
                        print("OpenBAO built and installed successfully!")
                        return True
                    else:
                        print("Build failed. You can try building manually or use vault.enabled=false")
                        sys.exit(1)  # Exit with error code to fail make install-dev
                else:
                    print("Skipping OpenBAO build.")
                    print("The development environment will work fine with vault.enabled=false")
                    return False
            except (KeyboardInterrupt, EOFError):
                print("\nSkipping OpenBAO build.")
                print("The development environment will work fine with vault.enabled=false")
                return False

    except FileNotFoundError:
        print(f"Package manager not found for {system}")

    return False


def install_from_binary():
    """Download and install OpenBAO from precompiled binary."""
    try:
        platform_str = detect_platform()
        print(f"Detected platform: {platform_str}")

        # BSD systems don't have precompiled binaries available
        if platform_str.startswith('openbsd') or platform_str.startswith('netbsd'):
            print(f"{platform_str.split('_')[0].capitalize()} precompiled binaries are not available from OpenBAO releases.")
            print("Please install manually or use the package manager option.")
            return False

        # Get the latest release version
        try:
            import json
            api_url = "https://api.github.com/repos/openbao/openbao/releases/latest"
            with urllib.request.urlopen(api_url) as response:
                release_data = json.loads(response.read().decode())
                version = release_data['tag_name']
                print(f"Latest version: {version}")
        except Exception as e:
            print(f"Could not fetch latest version: {e}")
            version = "v2.4.1"  # fallback to known version
            print(f"Using fallback version: {version}")

        # OpenBAO download URL pattern - try different naming conventions
        base_url = f"https://github.com/openbao/openbao/releases/download/{version}"

        # Try different filename patterns based on actual releases
        possible_filenames = []

        # Windows-specific patterns (capital W and x86_64 instead of amd64)
        if platform_str.startswith('windows'):
            arch = platform_str.split('_')[1]  # extract amd64 from windows_amd64
            # Map Windows amd64 to x86_64 for GitHub release naming
            if arch == 'amd64':
                github_arch = 'x86_64'
            elif arch == 'arm64':
                github_arch = 'arm64'
            elif arch == 'arm':
                github_arch = 'armv6'
            else:
                github_arch = arch
            possible_filenames.append(f"bao_{version.lstrip('v')}_Windows_{github_arch}.zip")

        # FreeBSD-specific tar.gz patterns (FreeBSD has capital F in filename)
        elif platform_str.startswith('freebsd'):
            arch = platform_str.split('_')[1]  # extract amd64 from freebsd_amd64
            # Map FreeBSD amd64 to x86_64 for GitHub release naming
            github_arch = 'x86_64' if arch == 'amd64' else arch
            possible_filenames.append(f"bao_{version.lstrip('v')}_Freebsd_{github_arch}.tar.gz")

        # Generic patterns for other platforms
        possible_filenames.extend([
            f"bao-hsm_{version.lstrip('v')}_{platform_str}.deb",  # Debian package
            f"bao-hsm_{version.lstrip('v')}_{platform_str}.pkg.tar.zst",  # Arch package
            f"bao_{platform_str}.zip",  # Generic zip
            f"openbao_{version.lstrip('v')}_{platform_str}.zip",  # Alternative naming
            f"openbao_{platform_str}.zip",  # Alternative naming
        ])

        downloaded_file = None

        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Try each filename pattern
            for filename in possible_filenames:
                download_url = f"{base_url}/{filename}"
                file_path = os.path.join(temp_dir, filename)

                print(f"Trying: {download_url}")
                try:
                    # Validate URL to ensure it's from official OpenBAO releases
                    parsed_url = urllib.parse.urlparse(download_url)
                    if not (parsed_url.scheme in ['https'] and
                           parsed_url.netloc == 'github.com' and
                           '/openbao/openbao/releases/download/' in parsed_url.path):
                        raise ValueError("Invalid download URL - not from official OpenBAO releases")

                    # Use requests library for better security
                    response = requests.get(download_url, timeout=30, stream=True)
                    response.raise_for_status()

                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    print("Download completed successfully!")
                    downloaded_file = file_path
                    break
                except Exception as e:
                    print(f"Failed: {e}")
                    continue

            if not downloaded_file:
                print("All download attempts failed.")
                print("You may need to download OpenBAO manually from:")
                print("https://github.com/openbao/openbao/releases")
                return False

            # Handle different file types
            if downloaded_file.endswith('.deb'):
                return install_deb_package(downloaded_file)
            elif downloaded_file.endswith('.pkg.tar.zst'):
                print("Arch package format not yet supported in this script")
                print("Please install manually with: sudo pacman -U " + downloaded_file)
                return False
            elif downloaded_file.endswith('.zip'):
                # Extract the binary from zip
                with zipfile.ZipFile(downloaded_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Find the binary (should be named 'bao' or 'bao.exe')
                binary_name = 'bao.exe' if platform.system().lower() == 'windows' else 'bao'
                binary_path = os.path.join(temp_dir, binary_name)

                if not os.path.exists(binary_path):
                    print(f"Binary {binary_name} not found in downloaded archive")
                    return False

                # Make binary executable (Unix-like systems)
                if platform.system().lower() != 'windows':
                    os.chmod(binary_path, 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions

                # Install to appropriate location
                install_path = get_install_path()
                if install_path:
                    target_path = os.path.join(install_path, binary_name)
                    print(f"Attempting to install to: {target_path}")
                    try:
                        # Ensure the directory exists
                        os.makedirs(install_path, exist_ok=True)
                        shutil.copy2(binary_path, target_path)
                        print(f"OpenBAO installed to: {target_path}")
                        return True
                    except PermissionError as e:
                        print(f"Permission denied installing to {install_path}: {e}")
                        print("You may need to run with appropriate privileges or install manually")
                        # Try alternative location
                        alt_path = os.path.normpath(os.path.expanduser("~/bin"))
                        if alt_path != install_path:
                            print(f"Trying alternative location: {alt_path}")
                            try:
                                os.makedirs(alt_path, exist_ok=True)
                                alt_target = os.path.join(alt_path, binary_name)
                                shutil.copy2(binary_path, alt_target)
                                print(f"OpenBAO installed to: {alt_target}")
                                print(f"Add {alt_path} to your PATH to use 'bao' command")
                                return True
                            except Exception as e2:
                                print(f"Alternative location also failed: {e2}")
                        return False
                else:
                    print("Could not determine appropriate installation path")
                    return False
            elif downloaded_file.endswith('.tar.gz'):
                # Extract the binary from tar.gz (used by FreeBSD)
                import tarfile
                with tarfile.open(downloaded_file, 'r:gz') as tar_ref:
                    # Safe extraction to prevent path traversal attacks
                    safe_extract(tar_ref, temp_dir)

                # Find the binary (should be named 'bao' or 'bao.exe')
                binary_name = 'bao.exe' if platform.system().lower() == 'windows' else 'bao'
                binary_path = os.path.join(temp_dir, binary_name)

                if not os.path.exists(binary_path):
                    print(f"Binary {binary_name} not found in downloaded archive")
                    return False

                # Make binary executable (Unix-like systems)
                if platform.system().lower() != 'windows':
                    os.chmod(binary_path, 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions

                # Install to appropriate location
                install_path = get_install_path()
                if install_path:
                    target_path = os.path.join(install_path, binary_name)
                    try:
                        shutil.copy2(binary_path, target_path)
                        print(f"OpenBAO installed to: {target_path}")
                        return True
                    except PermissionError:
                        print(f"Permission denied installing to {install_path}")
                        print("You may need to run with appropriate privileges or install manually")
                        return False
                else:
                    print("Could not determine appropriate installation path")
                    return False
            else:
                print(f"Unsupported file format: {downloaded_file}")
                return False

    except Exception as e:
        print(f"Binary installation failed: {e}")
        return False


def install_deb_package(deb_file):
    """Install OpenBAO from .deb package."""
    try:
        print("Installing OpenBAO .deb package...")
        result = subprocess.run(['sudo', 'dpkg', '-i', deb_file],
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("OpenBAO installed successfully via dpkg!")
            return True
        else:
            print(f"dpkg installation failed: {result.stderr}")
            # If sudo failed, try extracting manually
            if "sudo:" in result.stderr or "password" in result.stderr.lower():
                print("Cannot use sudo in this environment. Trying manual extraction...")
                return extract_from_deb(deb_file)

            # Try to fix dependencies
            print("Attempting to fix dependencies...")
            subprocess.run(['sudo', 'apt-get', 'install', '-f'],
                          capture_output=True)
            return check_openbao_installed()
    except FileNotFoundError:
        print("dpkg not found - not a Debian/Ubuntu system")
        return False
    except Exception as e:
        print(f"Error installing .deb package: {e}")
        return extract_from_deb(deb_file)


def extract_from_deb(deb_file):
    """Extract binary from .deb package manually."""
    try:
        import tempfile
        print("Extracting binary from .deb package...")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract .deb file (which is an ar archive)
            result = subprocess.run(['ar', 'x', deb_file],
                                   cwd=temp_dir, capture_output=True, text=True)
            if result.returncode != 0:
                print("ar command not available, trying alternative method...")
                return False

            # Find and extract data.tar.* file
            data_files = [f for f in os.listdir(temp_dir) if f.startswith('data.tar')]
            if not data_files:
                print("No data.tar file found in .deb package")
                return False

            data_file = os.path.join(temp_dir, data_files[0])
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir)

            # Extract the data archive
            if data_file.endswith('.xz'):
                subprocess.run(['tar', 'xf', data_file, '-C', extract_dir])
            elif data_file.endswith('.gz'):
                subprocess.run(['tar', 'xzf', data_file, '-C', extract_dir])
            else:
                subprocess.run(['tar', 'xf', data_file, '-C', extract_dir])

            # Find the bao binary
            for root, dirs, files in os.walk(extract_dir):
                if 'bao' in files:
                    binary_path = os.path.join(root, 'bao')

                    # Make executable
                    os.chmod(binary_path, 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions

                    # Install to user's local bin
                    install_path = os.path.expanduser("~/.local/bin")
                    os.makedirs(install_path, exist_ok=True)
                    target_path = os.path.join(install_path, 'bao')

                    shutil.copy2(binary_path, target_path)
                    print(f"OpenBAO extracted and installed to: {target_path}")
                    print("You may need to add ~/.local/bin to your PATH")
                    return True

            print("bao binary not found in .deb package")
            return False

    except Exception as e:
        print(f"Error extracting from .deb package: {e}")
        return False


def get_install_path():
    """Get appropriate installation path for the binary."""
    system = platform.system().lower()

    if system == 'windows':
        # Try common Windows paths with proper Windows path separators
        paths = [
            os.path.normpath(os.path.expanduser("~/AppData/Local/bin")),
            os.path.normpath("C:/Program Files/OpenBAO"),
            os.path.normpath(os.path.expanduser("~/bin")),
        ]
    else:
        # Unix-like systems
        paths = [
            "/usr/local/bin",
            os.path.expanduser("~/.local/bin"),
            "/opt/openbao/bin",
        ]

    # Check if any of these paths exist and are writable
    for path in paths:
        if os.path.exists(path) and os.access(path, os.W_OK):
            return path
        elif not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                if os.access(path, os.W_OK):
                    return path
            except:
                continue

    # Fallback to first path that we can create
    for path in paths:
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except:
            continue

    return None


def main():
    """Main installation function."""
    print("OpenBAO Installation Script")
    print("=" * 40)

    # Check if already installed
    if check_openbao_installed():
        return 0

    # Special handling for BSD systems
    system = platform.system().lower()
    if system in ['openbsd', 'netbsd']:
        print(f"{system.capitalize()} detected - trying package installation...")

        # Try package manager first (this will handle the build-from-source option)
        if install_via_package_manager():
            # Verify installation
            if check_openbao_installed():
                print("\nOpenBAO installation completed successfully!")
                return 0

        # If package manager returns False, it already handled the messaging
        print("\nContinuing with development setup (OpenBAO optional)...")
        return 0  # Exit gracefully instead of failing

    # For other platforms, try package manager first
    if install_via_package_manager():
        # Verify installation
        if check_openbao_installed():
            return 0

    # Fall back to binary installation
    print("\nFalling back to binary installation...")
    if install_from_binary():
        # First check if it's accessible via PATH
        if check_openbao_installed():
            print("\nOpenBAO installation completed successfully!")
            return 0

        # If not in PATH, check if it was installed to the expected location
        install_path = get_install_path()
        if install_path and check_openbao_at_path(install_path):
            print("\nOpenBAO installation completed successfully!")
            print(f"Note: OpenBAO installed to {install_path} but not in current PATH")
            print(f"Add {install_path} to your PATH or use the full path: {os.path.join(install_path, 'bao')}")
            return 0
        else:
            print("Installation completed but 'bao' command not found in PATH")
            print("You may need to add the installation directory to your PATH")
            return 1
    else:
        print("\nAutomatic installation failed.")
        print("Please install OpenBAO manually:")
        print("1. Visit: https://github.com/openbao/openbao/releases")
        print("2. Download the appropriate binary for your platform")
        print("3. Extract and place 'bao' binary in your PATH")
        return 1


if __name__ == "__main__":
    sys.exit(main())