#!/usr/bin/env python3
"""
OpenTelemetry and Prometheus installation script for SysManage development environment.
Automatically detects platform and installs components accordingly.
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

import requests


def safe_extract_tar(tar, path):
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


def safe_extract_zip(zip_file, path):
    """Safely extract zip file, preventing path traversal attacks."""
    def is_within_directory(directory, target):
        abs_directory = os.path.abspath(directory)
        abs_target = os.path.abspath(target)
        prefix = os.path.commonpath([abs_directory, abs_target])
        return prefix == abs_directory

    for member in zip_file.namelist():
        if is_within_directory(path, os.path.join(path, member)):
            zip_file.extract(member, path)


def detect_platform():
    """Detect the current platform and return appropriate binary info."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map Python's machine names to standard naming convention
    if machine in ['x86_64', 'amd64']:
        arch = 'amd64'
    elif machine in ['aarch64', 'arm64']:
        arch = 'arm64'
    elif machine in ['armv7l', 'armv6l']:
        arch = 'arm'
    else:
        arch = machine

    if system == 'linux':
        platform_name = 'linux'
    elif system == 'darwin':
        platform_name = 'darwin'
    elif system == 'windows':
        platform_name = 'windows'
    else:
        platform_name = system

    return platform_name, arch


def check_system_requirements():
    """Check if the system has required dependencies."""
    print("🔍 Checking system requirements...")

    # Check if we're on a supported system
    system = platform.system().lower()
    if system not in ['linux', 'darwin', 'windows']:
        print(f"❌ Unsupported operating system: {system}")
        return False

    # Check if we have required tools
    required_tools = ['curl', 'tar']
    if system == 'windows':
        required_tools = ['curl', 'tar']  # Windows 10+ has these built-in

    for tool in required_tools:
        if not shutil.which(tool):
            print(f"❌ Required tool not found: {tool}")
            return False

    print("✅ System requirements met")
    return True


def install_prometheus():
    """Install Prometheus if not already installed."""
    print("\n🔧 Installing Prometheus...")

    # Check if Prometheus is already installed
    if shutil.which('prometheus'):
        print("✅ Prometheus is already installed")
        return True

    try:
        platform_name, arch = detect_platform()
        version = "2.48.0"  # Latest stable version

        if platform_name == 'windows':
            filename = f"prometheus-{version}.windows-{arch}.zip"
            url = f"https://github.com/prometheus/prometheus/releases/download/v{version}/{filename}"
            extract_func = safe_extract_zip
        else:
            filename = f"prometheus-{version}.{platform_name}-{arch}.tar.gz"
            url = f"https://github.com/prometheus/prometheus/releases/download/v{version}/{filename}"
            extract_func = safe_extract_tar

        print(f"Downloading Prometheus {version} for {platform_name}-{arch}...")

        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = os.path.join(temp_dir, filename)

            # Download
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()

            with open(archive_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Extract
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            if platform_name == 'windows':
                with zipfile.ZipFile(archive_path, 'r') as zip_file:
                    extract_func(zip_file, extract_dir)
            else:
                with tarfile.open(archive_path, 'r:gz') as tar:
                    extract_func(tar, extract_dir)

            # Find the extracted directory
            extracted_contents = os.listdir(extract_dir)
            if not extracted_contents:
                raise Exception("No files found in extracted archive")

            prometheus_dir = os.path.join(extract_dir, extracted_contents[0])

            # Install to /usr/local/bin (or appropriate location)
            install_dir = "/usr/local/bin"
            if platform_name == 'windows':
                install_dir = r"C:\Program Files\SysManage\bin"
                os.makedirs(install_dir, exist_ok=True)

            prometheus_binary = "prometheus.exe" if platform_name == 'windows' else "prometheus"
            promtool_binary = "promtool.exe" if platform_name == 'windows' else "promtool"

            # Copy binaries
            shutil.copy2(
                os.path.join(prometheus_dir, prometheus_binary),
                os.path.join(install_dir, prometheus_binary)
            )
            shutil.copy2(
                os.path.join(prometheus_dir, promtool_binary),
                os.path.join(install_dir, promtool_binary)
            )

            # Make executable on Unix-like systems
            if platform_name != 'windows':
                os.chmod(os.path.join(install_dir, prometheus_binary), 0o755)
                os.chmod(os.path.join(install_dir, promtool_binary), 0o755)

        print("✅ Prometheus installed successfully")
        return True

    except Exception as e:
        print(f"❌ Failed to install Prometheus: {e}")
        return False


def install_otel_collector():
    """Install OpenTelemetry Collector if not already installed."""
    print("\n🔧 Installing OpenTelemetry Collector...")

    # Check if OTEL Collector is already installed
    if shutil.which('otelcol-contrib'):
        print("✅ OpenTelemetry Collector is already installed")
        return True

    try:
        platform_name, arch = detect_platform()
        version = "0.91.0"  # Latest stable version

        if platform_name == 'linux':
            # Use .deb package for Ubuntu/Debian
            if os.path.exists('/etc/debian_version'):
                filename = f"otelcol-contrib_{version}_linux_{arch}.deb"
                url = f"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{version}/{filename}"

                print(f"Downloading OpenTelemetry Collector {version} for {platform_name}-{arch}...")

                with tempfile.TemporaryDirectory() as temp_dir:
                    deb_path = os.path.join(temp_dir, filename)

                    # Download
                    response = requests.get(url, stream=True, timeout=300)
                    response.raise_for_status()

                    with open(deb_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Install using dpkg
                    subprocess.run(['sudo', 'dpkg', '-i', deb_path], check=True)

                    # Enable and start the service
                    subprocess.run(['sudo', 'systemctl', 'enable', 'otelcol-contrib'], check=True)
                    print("📝 OpenTelemetry Collector service enabled")

            else:
                # Generic Linux - download binary
                filename = f"otelcol-contrib_{version}_{platform_name}_{arch}.tar.gz"
                url = f"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{version}/{filename}"

                print(f"Downloading OpenTelemetry Collector {version} for {platform_name}-{arch}...")

                with tempfile.TemporaryDirectory() as temp_dir:
                    archive_path = os.path.join(temp_dir, filename)

                    # Download
                    response = requests.get(url, stream=True, timeout=300)
                    response.raise_for_status()

                    with open(archive_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Extract
                    with tarfile.open(archive_path, 'r:gz') as tar:
                        safe_extract_tar(tar, temp_dir)

                    # Install to /usr/local/bin
                    shutil.copy2(
                        os.path.join(temp_dir, 'otelcol-contrib'),
                        '/usr/local/bin/otelcol-contrib'
                    )
                    os.chmod('/usr/local/bin/otelcol-contrib', 0o755)

        elif platform_name == 'darwin':
            # macOS
            filename = f"otelcol-contrib_{version}_{platform_name}_{arch}.tar.gz"
            url = f"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{version}/{filename}"

            print(f"Downloading OpenTelemetry Collector {version} for {platform_name}-{arch}...")

            with tempfile.TemporaryDirectory() as temp_dir:
                archive_path = os.path.join(temp_dir, filename)

                # Download
                response = requests.get(url, stream=True, timeout=300)
                response.raise_for_status()

                with open(archive_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Extract
                with tarfile.open(archive_path, 'r:gz') as tar:
                    safe_extract_tar(tar, temp_dir)

                # Install to /usr/local/bin
                shutil.copy2(
                    os.path.join(temp_dir, 'otelcol-contrib'),
                    '/usr/local/bin/otelcol-contrib'
                )
                os.chmod('/usr/local/bin/otelcol-contrib', 0o755)

        else:
            print(f"❌ Unsupported platform for OTEL Collector: {platform_name}")
            return False

        print("✅ OpenTelemetry Collector installed successfully")
        return True

    except Exception as e:
        print(f"❌ Failed to install OpenTelemetry Collector: {e}")
        return False


def create_config_directories():
    """Create necessary configuration directories."""
    print("\n📁 Creating configuration directories...")

    config_dirs = [
        '/etc/otelcol-contrib',
        '/etc/prometheus',
        '/var/lib/prometheus',
        '/var/log/prometheus'
    ]

    for config_dir in config_dirs:
        try:
            os.makedirs(config_dir, exist_ok=True, mode=0o755)
            print(f"✅ Created directory: {config_dir}")
        except PermissionError:
            try:
                subprocess.run(['sudo', 'mkdir', '-p', config_dir], check=True)
                subprocess.run(['sudo', 'chmod', '755', config_dir], check=True)
                print(f"✅ Created directory (with sudo): {config_dir}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to create directory {config_dir}: {e}")
                return False

    return True


def install_python_packages():
    """Install required Python packages for OpenTelemetry."""
    print("\n🐍 Installing Python OpenTelemetry packages...")

    packages = [
        'opentelemetry-api>=1.25.0,<2.0.0',
        'opentelemetry-sdk>=1.25.0,<2.0.0',
        'opentelemetry-instrumentation>=0.46b0,<1.0.0',
        'opentelemetry-exporter-otlp>=1.25.0,<2.0.0',
        'opentelemetry-instrumentation-fastapi>=0.46b0,<1.0.0',
        'opentelemetry-instrumentation-sqlalchemy>=0.46b0,<1.0.0',
        'opentelemetry-instrumentation-requests>=0.46b0,<1.0.0',
        'opentelemetry-instrumentation-logging>=0.46b0,<1.0.0',
        'opentelemetry-exporter-prometheus>=0.46b0,<1.0.0'
    ]

    try:
        # Find pip in virtual environment
        venv_path = Path(__file__).parent.parent / '.venv'
        if venv_path.exists():
            if platform.system() == 'Windows':
                pip_path = venv_path / 'Scripts' / 'pip.exe'
            else:
                pip_path = venv_path / 'bin' / 'pip'
        else:
            pip_path = shutil.which('pip') or shutil.which('pip3')

        if not pip_path or not os.path.exists(pip_path):
            print("❌ pip not found. Please ensure virtual environment is set up.")
            return False

        # Install packages
        cmd = [str(pip_path), 'install'] + packages
        subprocess.run(cmd, check=True)

        print("✅ Python OpenTelemetry packages installed successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Python packages: {e}")
        return False


def main():
    """Main installation function."""
    print("🚀 SysManage Telemetry Stack Installation")
    print("=========================================")
    print("This will install:")
    print("  • OpenTelemetry Collector")
    print("  • Prometheus")
    print("  • Python OpenTelemetry packages")
    print()

    # Check system requirements
    if not check_system_requirements():
        sys.exit(1)

    # Check for elevated privileges
    if platform.system() != 'Windows' and os.geteuid() != 0:
        print("❌ This script requires elevated privileges.")
        print("Please run: sudo python3 scripts/install-telemetry.py")
        sys.exit(1)

    success_count = 0
    total_steps = 5

    # Install components
    if create_config_directories():
        success_count += 1

    if install_prometheus():
        success_count += 1

    if install_otel_collector():
        success_count += 1

    if install_python_packages():
        success_count += 1

    # Final success check
    if success_count == total_steps:
        success_count += 1
        print("\n🎉 Telemetry stack installation completed successfully!")
        print("\nNext steps:")
        print("  1. Configure OpenTelemetry Collector (/etc/otelcol-contrib/config.yaml)")
        print("  2. Configure Prometheus (/etc/prometheus/prometheus.yml)")
        print("  3. Start services with: make start-telemetry")
        print("  4. Enable Grafana integration in SysManage settings")
    else:
        print(f"\n⚠️  Installation partially completed ({success_count}/{total_steps} steps)")
        print("Please check error messages above and retry failed components.")
        sys.exit(1)


if __name__ == '__main__':
    main()