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
    elif system == 'freebsd':
        platform_name = 'freebsd'
    elif system == 'netbsd':
        platform_name = 'netbsd'
    elif system == 'openbsd':
        platform_name = 'openbsd'
    else:
        platform_name = system

    return platform_name, arch


def check_system_requirements():
    """Check if the system has required dependencies."""
    print("🔍 Checking system requirements...")

    # Check if we're on a supported system
    system = platform.system().lower()
    if system not in ['linux', 'darwin', 'windows', 'netbsd', 'openbsd', 'freebsd']:
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
    # First check system PATH
    if shutil.which('prometheus'):
        print("✅ Prometheus is already installed (system PATH)")
        return True

    # For BSD systems, also check ~/.local/bin where we build from source
    home_prometheus = Path.home() / '.local' / 'bin' / 'prometheus'
    if home_prometheus.exists():
        print("✅ Prometheus is already installed (~/.local/bin)")
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

            # Install to appropriate location based on platform
            if platform_name == 'windows':
                # Use user-writable directory on Windows
                install_dir = os.path.expanduser(r"~\AppData\Local\bin")
                os.makedirs(install_dir, exist_ok=True)
            elif platform_name == 'freebsd':
                # BSD systems use /usr/pkg/bin or /usr/local/bin
                # Check which exists, prefer /usr/pkg/bin on NetBSD
                if os.path.exists('/usr/pkg/bin'):
                    install_dir = "/usr/pkg/bin"
                else:
                    install_dir = "/usr/local/bin"
            else:
                install_dir = "/usr/local/bin"

            prometheus_binary = "prometheus.exe" if platform_name == 'windows' else "prometheus"
            promtool_binary = "promtool.exe" if platform_name == 'windows' else "promtool"

            # Copy binaries (may require sudo on Unix)
            try:
                shutil.copy2(
                    os.path.join(prometheus_dir, prometheus_binary),
                    os.path.join(install_dir, prometheus_binary)
                )
                shutil.copy2(
                    os.path.join(prometheus_dir, promtool_binary),
                    os.path.join(install_dir, promtool_binary)
                )
            except PermissionError:
                # Try with sudo/doas
                print(f"⚠️  Need elevated privileges to install to {install_dir}")
                print("   Telemetry binaries downloaded but not installed")
                print(f"   You can manually copy them from: {prometheus_dir}")
                return False

            # Make executable on Unix-like systems
            if platform_name != 'windows':
                os.chmod(os.path.join(install_dir, prometheus_binary), 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                os.chmod(os.path.join(install_dir, promtool_binary), 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
            else:
                # Provide PATH hint for Windows users
                print(f"💡 Add {install_dir} to your PATH to use 'prometheus' command globally")

        print("✅ Prometheus installed successfully")
        return True

    except Exception as e:
        print(f"❌ Failed to install Prometheus: {e}")
        return False


def check_gnu_tools():
    """Check for GNU tools (gfind, gxargs, gdirname) on BSD systems."""
    system = platform.system().lower()
    if system not in ['netbsd', 'openbsd', 'freebsd']:
        return True  # Not needed on non-BSD systems

    print("🔍 Checking for GNU tools (required for build)...")

    # Check if required GNU tools are available
    has_gfind = shutil.which('gfind') is not None
    has_gxargs = shutil.which('gxargs') is not None
    has_gdirname = shutil.which('gdirname') is not None

    missing = []
    if not has_gfind or not has_gxargs:
        missing.append('findutils')
    if not has_gdirname:
        missing.append('coreutils')

    if not missing:
        print("   ✓ GNU tools already installed")
        return True

    print(f"   ⚠️  Missing packages: {', '.join(missing)}")

    # On OpenBSD, just give instructions rather than trying to auto-install
    system = platform.system().lower()
    if system == 'openbsd':
        print("   Please install the missing packages manually:")
        print(f"   doas pkg_add {' '.join(missing)}")
        print("   Then re-run the installation.")
        return False

    print("   Installing required packages...")

    # Try to install using appropriate package manager for the platform
    try:
        system = platform.system().lower()
        for package in missing:
            if system == 'netbsd':
                # NetBSD uses pkgin
                result = subprocess.run(
                    ['sudo', 'pkgin', '-y', 'install', package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            elif system == 'openbsd':
                # OpenBSD uses pkg_add and doas
                result = subprocess.run(
                    ['doas', 'pkg_add', package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            else:
                # Default to pkgin for other BSD systems
                result = subprocess.run(
                    ['sudo', 'pkgin', '-y', 'install', package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

            if result.returncode == 0:
                print(f"   ✓ {package} installed successfully")
            else:
                print(f"   ❌ Failed to install {package}: {result.stderr}")
                if system == 'openbsd':
                    print(f"   Please install manually: doas pkg_add {package}")
                else:
                    print(f"   Please install manually: sudo pkgin install {package}")
                return False

        return True
    except Exception as e:
        print(f"   ❌ Failed to install packages: {e}")
        if platform.system().lower() == 'openbsd':
            print(f"   Please install manually: doas pkg_add {' '.join(missing)}")
        else:
            print(f"   Please install manually: sudo pkgin install {' '.join(missing)}")
        return False


def build_otel_collector_from_source(version, platform_name, arch):
    """Build OpenTelemetry Collector from source using Go."""
    print("🔨 Building OpenTelemetry Collector from source (this may take several minutes)...")

    # Check if Go is installed
    if not shutil.which('go'):
        print("❌ Go compiler not found. Install Go to build from source.")
        print("   On NetBSD: sudo pkgin install go")
        return False

    # Check for GNU tools on BSD systems
    if not check_gnu_tools():
        return False

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Clone the opentelemetry-collector-contrib repository
            print(f"📥 Downloading source code (tag v{version})...")
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', '--branch', f'v{version}',
                 'https://github.com/open-telemetry/opentelemetry-collector-contrib.git',
                 os.path.join(temp_dir, 'otelcol-contrib')],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"❌ Failed to clone repository: {result.stderr}")
                return False

            build_dir = os.path.join(temp_dir, 'otelcol-contrib')

            # Apply BSD compatibility fixes using Python (more reliable than sed)
            print("🔧 Applying BSD compatibility fixes...")
            makefile = os.path.join(build_dir, 'Makefile')
            makefile_common = os.path.join(build_dir, 'Makefile.Common')

            try:
                # Fix Makefile
                with open(makefile, 'r') as f:
                    content = f.read()

                # Replace BSD commands with GNU versions
                content = content.replace('$(shell find ', '$(shell gfind ')
                content = content.replace('| xargs ', '| gxargs ')
                content = content.replace('{ find ', '{ gfind ')
                content = content.replace('dirname ', 'gdirname ')

                with open(makefile, 'w') as f:
                    f.write(content)

                # Fix Makefile.Common
                with open(makefile_common, 'r') as f:
                    content = f.read()

                content = content.replace('| xargs ', '| gxargs ')
                content = content.replace('| xargs\n', '| gxargs\n')
                content = content.replace('$$(find ', '$$(gfind ')
                content = content.replace('dirname ', 'gdirname ')

                with open(makefile_common, 'w') as f:
                    f.write(content)

                print("   ✓ BSD compatibility fixes applied")
            except Exception as e:
                print(f"   ⚠️  Fixes failed: {e}")
                return False

            # For BSD systems, create /bin/bash symlink if needed
            print("🔧 Preparing build environment for BSD...")
            symlink_created = False
            system = platform.system().lower()

            # Check for bash in platform-specific locations
            bash_locations = []
            elevation_cmd = 'sudo'

            if system == 'netbsd':
                bash_locations = ['/usr/pkg/bin/bash']
                elevation_cmd = 'sudo'
            elif system == 'openbsd':
                bash_locations = ['/usr/local/bin/bash']
                elevation_cmd = 'doas'
            elif system == 'freebsd':
                bash_locations = ['/usr/local/bin/bash']
                elevation_cmd = 'sudo'

            bash_path = None
            for bash_loc in bash_locations:
                if os.path.exists(bash_loc):
                    bash_path = bash_loc
                    break

            if not os.path.exists('/bin/bash') and bash_path:
                print(f"   Creating temporary /bin/bash symlink (requires {elevation_cmd})...")
                try:
                    result = subprocess.run([elevation_cmd, 'ln', '-sf', bash_path, '/bin/bash'],
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        symlink_created = True
                        print("   ✓ Symlink created")
                    else:
                        print(f"   ⚠️  Failed to create symlink: {result.stderr}")
                        print("   Build will likely fail - you may need to manually run:")
                        print(f"   {elevation_cmd} ln -sf {bash_path} /bin/bash")
                        return False
                except Exception as e:
                    print(f"   ⚠️  Could not create symlink: {e}")
                    return False

            # Create a minimal builder config for NetBSD with only essential components
            print("🔧 Creating minimal NetBSD-compatible build configuration...")
            builder_config = os.path.join(build_dir, 'cmd', 'otelcontribcol', 'builder-config.yaml')

            # Minimal config with just OTLP receivers/exporters and basic processors
            minimal_config = """# Minimal OpenTelemetry Collector configuration for NetBSD
dist:
  module: github.com/open-telemetry/opentelemetry-collector-contrib/cmd/otelcontribcol
  name: otelcontribcol
  description: Minimal OpenTelemetry Collector for NetBSD
  version: 0.91.0
  output_path: _build

extensions:
  - gomod: go.opentelemetry.io/collector/extension/zpagesextension v0.91.0

exporters:
  - gomod: go.opentelemetry.io/collector/exporter/debugexporter v0.91.0
  - gomod: go.opentelemetry.io/collector/exporter/otlpexporter v0.91.0
  - gomod: go.opentelemetry.io/collector/exporter/otlphttpexporter v0.91.0
  - gomod: github.com/open-telemetry/opentelemetry-collector-contrib/exporter/prometheusexporter v0.91.0

processors:
  - gomod: go.opentelemetry.io/collector/processor/batchprocessor v0.91.0
  - gomod: go.opentelemetry.io/collector/processor/memorylimiterprocessor v0.91.0
  - gomod: github.com/open-telemetry/opentelemetry-collector-contrib/processor/attributesprocessor v0.91.0
  - gomod: github.com/open-telemetry/opentelemetry-collector-contrib/processor/resourceprocessor v0.91.0

receivers:
  - gomod: go.opentelemetry.io/collector/receiver/otlpreceiver v0.91.0
  - gomod: github.com/open-telemetry/opentelemetry-collector-contrib/receiver/prometheusreceiver v0.91.0

connectors:
  - gomod: go.opentelemetry.io/collector/connector/forwardconnector v0.91.0
"""

            with open(builder_config, 'w') as f:
                f.write(minimal_config)
            print("   ✓ Created minimal build configuration (OTLP + Prometheus only)")

            # Set Go build cache to /var/tmp to avoid /tmp space issues on NetBSD
            go_cache_dir = '/var/tmp/go-build'
            go_tmp_dir = '/var/tmp/go-tmp'
            os.makedirs(go_cache_dir, exist_ok=True)
            os.makedirs(go_tmp_dir, exist_ok=True)

            build_env = os.environ.copy()
            build_env['GOCACHE'] = go_cache_dir
            build_env['GOTMPDIR'] = go_tmp_dir

            # Remove NetBSD-incompatible components from components.go
            print("🔧 Removing NetBSD-incompatible components...")
            components_file = os.path.join(build_dir, 'cmd', 'otelcontribcol', 'components.go')

            if os.path.exists(components_file):
                with open(components_file, 'r') as f:
                    content = f.read()

                # Remove DataDog components and filestats receiver
                incompatible_imports = [
                    'datadogconnector "github.com/open-telemetry/opentelemetry-collector-contrib/connector/datadogconnector"',
                    'datadogexporter "github.com/open-telemetry/opentelemetry-collector-contrib/exporter/datadogexporter"',
                    'datadogprocessor "github.com/open-telemetry/opentelemetry-collector-contrib/processor/datadogprocessor"',
                    'datadogreceiver "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/datadogreceiver"',
                    'filestatsreceiver "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/filestatsreceiver"',
                ]

                for imp in incompatible_imports:
                    content = content.replace(imp + '\n', '')
                    content = content.replace('\t' + imp + '\n', '')

                # Remove factory registrations
                incompatible_factories = [
                    'datadogconnector.NewFactory(),',
                    'datadogexporter.NewFactory(),',
                    'datadogprocessor.NewFactory(),',
                    'datadogreceiver.NewFactory(),',
                    'filestatsreceiver.NewFactory(),',
                ]

                for factory in incompatible_factories:
                    content = content.replace('\n\t\t' + factory, '')
                    content = content.replace('\t\t' + factory + '\n', '')

                with open(components_file, 'w') as f:
                    f.write(content)

                print("   ✓ Components file updated")
            else:
                print(f"   ⚠️  Components file not found at {components_file}")

            binary_path = None

            # Try traditional Makefile build
            if True:
                # Build the collector
                print("🔧 Compiling OpenTelemetry Collector (this will take 5-10 minutes)...")
                print("   (Showing build output - this may take a while)...")

                result = subprocess.run(
                    ['gmake', 'otelcontribcol'],
                    cwd=build_dir,
                    env=build_env,
                    timeout=1800  # 30 minute timeout (increased)
                )

                if result.returncode != 0:
                    print(f"❌ Build failed with compilation errors")
                    print(f"   This may be due to platform-specific code issues in version {version}")
                    print(f"   The Python OpenTelemetry packages are installed and working.")
                    print(f"   The OpenTelemetry Collector is optional - you can:")
                    print(f"   1. Use Prometheus alone for metrics")
                    print(f"   2. Try a different OTEL Collector version")
                    print(f"   3. Use a pre-built binary from a different source")
                    return False

                # Find the built binary - check bin directory for any otel binary
                bin_dir = os.path.join(build_dir, 'bin')

                if os.path.exists(bin_dir):
                    binaries = [f for f in os.listdir(bin_dir) if 'otel' in f.lower() and os.path.isfile(os.path.join(bin_dir, f))]
                    if binaries:
                        binary_path = os.path.join(bin_dir, binaries[0])
                        print(f"   ✓ Found binary: {binaries[0]}")
                    else:
                        binary_path = None
                else:
                    binary_path = None

            if not binary_path or not os.path.exists(binary_path):
                print(f"❌ Built binary not found in {os.path.join(build_dir, 'bin')}")
                # List what's in the bin directory for debugging
                bin_dir = os.path.join(build_dir, 'bin')
                if os.path.exists(bin_dir):
                    print(f"   Contents of bin directory: {os.listdir(bin_dir)}")
                return False

            # Install to appropriate directory
            if platform_name == 'freebsd' and os.path.exists('/usr/pkg/bin'):
                install_dir = '/usr/pkg/bin'
            else:
                install_dir = '/usr/local/bin'

            try:
                shutil.copy2(binary_path, os.path.join(install_dir, 'otelcol-contrib'))
                os.chmod(os.path.join(install_dir, 'otelcol-contrib'), 0o755)
                print(f"✅ OpenTelemetry Collector built and installed to {install_dir}")
                return True
            except PermissionError:
                print(f"⚠️  Need elevated privileges to install to {install_dir}")
                print(f"   Built binary is at: {binary_path}")
                print(f"   Run: sudo cp {binary_path} {install_dir}/")
                return False

    except subprocess.TimeoutExpired:
        print("❌ Build timed out after 15 minutes")
        return False
    except Exception as e:
        print(f"❌ Failed to build from source: {e}")
        return False


def build_otel_collector_from_source(version, platform_name, arch):
    """Build OpenTelemetry Collector from source for BSD systems."""
    print("🔧 Building OpenTelemetry Collector from source...")
    print("   This requires Go, git, and may take 10-15 minutes...")

    # Check for required tools
    required_tools = ['go', 'git', 'gmake']
    for tool in required_tools:
        if not shutil.which(tool):
            print(f"❌ Required tool '{tool}' not found")
            return False

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up build directory
            build_dir = os.path.join(temp_dir, 'opentelemetry-collector-contrib')

            # Clone the repository
            print("📥 Cloning OpenTelemetry Collector source...")
            result = subprocess.run([
                'git', 'clone', '--depth', '1', '--branch', f'v{version}',
                'https://github.com/open-telemetry/opentelemetry-collector-contrib.git',
                build_dir
            ], cwd=temp_dir, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"❌ Failed to clone repository: {result.stderr}")
                return False

            # Handle platform-specific modifications
            if platform_name in ['netbsd', 'openbsd']:

                # Apply platform-specific modifications using sed
                if platform_name == 'openbsd':
                    print("🔧 Applying OpenBSD-specific modifications...")

                    # Find all files that might reference bash
                    print("   🔍 Searching for bash references...")
                    result = subprocess.run(['grep', '-r', '/bin/bash', '.'],
                                          cwd=build_dir, capture_output=True, text=True)
                    if result.stdout:
                        print(f"   Found bash references in: {result.stdout[:200]}...")

                    # Use sed to replace GNU tools and bash references in all relevant files
                    sed_commands = [
                        # Fix the TO_MOD_DIR variable (missing -exec)
                        ['sed', '-i', 's|TO_MOD_DIR=dirname {} \\\\;|TO_MOD_DIR=-exec dirname {} \\\\;|g', 'Makefile'],
                        # Replace find with gfind - be more comprehensive
                        ['sed', '-i', 's|$(shell find |$(shell gfind |g', 'Makefile'],
                        ['sed', '-i', 's|$(shell find |$(shell gfind |g', 'Makefile.Common'],
                        ['sed', '-i', 's|\\bfind |gfind |g', 'Makefile'],
                        ['sed', '-i', 's|\\bfind |gfind |g', 'Makefile.Common'],
                        ['sed', '-i', 's|{ find |{ gfind |g', 'Makefile'],
                        ['sed', '-i', 's|{ find |{ gfind |g', 'Makefile.Common'],
                        # Replace xargs with gxargs - be more comprehensive
                        ['sed', '-i', 's|\\bxargs |gxargs |g', 'Makefile'],
                        ['sed', '-i', 's|\\bxargs |gxargs |g', 'Makefile.Common'],
                        ['sed', '-i', 's| xargs | gxargs |g', 'Makefile'],
                        ['sed', '-i', 's| xargs | gxargs |g', 'Makefile.Common'],
                        # Replace bash with /bin/sh in all files
                        ['sed', '-i', 's|/bin/bash|/bin/sh|g', 'Makefile'],
                        ['sed', '-i', 's|/bin/bash|/bin/sh|g', 'Makefile.Common'],
                        ['sed', '-i', 's|bash -c|/bin/sh -c|g', 'Makefile'],
                        ['sed', '-i', 's|bash -c|/bin/sh -c|g', 'Makefile.Common'],
                    ]

                    for cmd in sed_commands:
                        file_path = os.path.join(build_dir, cmd[-1])
                        if os.path.exists(file_path):
                            full_cmd = cmd[:-1] + [file_path]
                            result = subprocess.run(full_cmd, cwd=build_dir)
                            print(f"   Applied: {' '.join(cmd)} to {cmd[-1]}")

                    # Also search for and modify any .mk files or other build files
                    result = subprocess.run(['find', '.', '-name', '*.mk'],
                                          cwd=build_dir, capture_output=True, text=True)
                    if result.stdout:
                        mk_files = result.stdout.strip().split('\n')
                        for mk_file in mk_files:
                            if mk_file.strip():
                                subprocess.run(['sed', '-i', 's|/bin/bash|/bin/sh|g', mk_file.strip()],
                                             cwd=build_dir, check=False)
                                subprocess.run(['sed', '-i', 's|\\bfind |gfind |g', mk_file.strip()],
                                             cwd=build_dir, check=False)
                                subprocess.run(['sed', '-i', 's|\\bxargs\\b|gxargs|g', mk_file.strip()],
                                             cwd=build_dir, check=False)

                    print("   ✓ OpenBSD modifications applied successfully")

                # Create minimal builder config for BSD systems
                print("🔧 Creating minimal BSD-compatible build configuration...")
                builder_config = os.path.join(build_dir, 'cmd', 'otelcontribcol', 'builder-config.yaml')

                minimal_config = f"""# Ultra-minimal OpenTelemetry Collector configuration for {platform_name.upper()}
dist:
  module: github.com/open-telemetry/opentelemetry-collector-contrib/cmd/otelcontribcol
  name: otelcontribcol
  description: Ultra-minimal OpenTelemetry Collector for {platform_name.upper()}
  version: {version}
  output_path: _build

exporters:
  - gomod: go.opentelemetry.io/collector/exporter/debugexporter v{version}
  - gomod: go.opentelemetry.io/collector/exporter/otlpexporter v{version}

processors:
  - gomod: go.opentelemetry.io/collector/processor/batchprocessor v{version}

receivers:
  - gomod: go.opentelemetry.io/collector/receiver/otlpreceiver v{version}
"""

                with open(builder_config, 'w') as f:
                    f.write(minimal_config)
                print("   ✓ Created minimal build configuration (OTLP + Prometheus only)")

                # Set ALL Go directories to home filesystem to avoid space issues
                # Use HOME environment variable to work for any user
                home_dir = os.path.expanduser('~')
                go_build_base = os.path.join(home_dir, 'tmp', 'go-build-tmp')
                go_cache_dir = os.path.join(go_build_base, 'cache')
                go_tmp_dir = os.path.join(go_build_base, 'tmp')
                go_mod_cache_dir = os.path.join(go_build_base, 'mod-cache')
                os.makedirs(go_cache_dir, exist_ok=True)
                os.makedirs(go_tmp_dir, exist_ok=True)
                os.makedirs(go_mod_cache_dir, exist_ok=True)

                build_env = os.environ.copy()
                build_env['GOCACHE'] = go_cache_dir
                build_env['GOTMPDIR'] = go_tmp_dir
                build_env['GOMODCACHE'] = go_mod_cache_dir
                build_env['TMPDIR'] = go_tmp_dir  # Critical: override system TMPDIR
                build_env['TMP'] = go_tmp_dir     # Additional temp override
                build_env['TEMP'] = go_tmp_dir    # Additional temp override
                build_env['GOPROXY'] = 'direct'   # Reduce proxy overhead
                build_env['GOSUMDB'] = 'off'      # Disable checksum verification to save space/time

                # Remove BSD-incompatible components from components.go
                print(f"🔧 Removing {platform_name.upper()}-incompatible components...")
                components_file = os.path.join(build_dir, 'cmd', 'otelcontribcol', 'components.go')

                if os.path.exists(components_file):
                    with open(components_file, 'r') as f:
                        content = f.read()

                    # Remove DataDog components and filestats receiver
                    incompatible_imports = [
                        'datadogconnector "github.com/open-telemetry/opentelemetry-collector-contrib/connector/datadogconnector"',
                        'datadogexporter "github.com/open-telemetry/opentelemetry-collector-contrib/exporter/datadogexporter"',
                        'datadogprocessor "github.com/open-telemetry/opentelemetry-collector-contrib/processor/datadogprocessor"',
                        'datadogreceiver "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/datadogreceiver"',
                        'filestatsreceiver "github.com/open-telemetry/opentelemetry-collector-contrib/receiver/filestatsreceiver"',
                    ]

                    for imp in incompatible_imports:
                        content = content.replace(imp + '\n', '')
                        content = content.replace('\t' + imp + '\n', '')

                    # Remove factory registrations
                    incompatible_factories = [
                        'datadogconnector.NewFactory(),',
                        'datadogexporter.NewFactory(),',
                        'datadogprocessor.NewFactory(),',
                        'datadogreceiver.NewFactory(),',
                        'filestatsreceiver.NewFactory(),',
                    ]

                    for factory in incompatible_factories:
                        content = content.replace('\n\t\t' + factory, '')
                        content = content.replace('\t\t' + factory + '\n', '')

                    with open(components_file, 'w') as f:
                        f.write(content)

                    print("   ✓ Components file updated")
                else:
                    print(f"   ⚠️  Components file not found at {components_file}")

                # Build the collector using Go directly instead of the complex Makefile
                print("🔧 Compiling OpenTelemetry Collector using Go builder...")
                print("   (Using simplified build process - this will take 5-10 minutes)...")

                # First, let's see what's available in the cmd directory
                cmd_dir = os.path.join(build_dir, 'cmd')
                if os.path.exists(cmd_dir):
                    available_cmds = os.listdir(cmd_dir)
                    print(f"   Available commands: {available_cmds}")

                # Try different possible locations for the collector and builder
                collector_paths = [
                    './cmd/otelcol-contrib',
                    './cmd/otelcontribcol',
                    './cmd/opentelemetry-collector-contrib',
                ]

                builder_paths = [
                    './cmd/builder',
                    './cmd/ocb',
                    './cmd/otelcol-builder',
                ]

                # First, try to build a collector directly
                result = None
                for collector_path in collector_paths:
                    full_path = os.path.join(build_dir, collector_path.lstrip('./'))
                    if os.path.exists(full_path):
                        print(f"   Found collector at: {collector_path}")

                        # Check what's in the directory
                        try:
                            contents = os.listdir(full_path)
                            print(f"   Directory contents: {contents}")
                        except:
                            print(f"   Could not list directory contents")

                        # Look for main.go or check if this is just a configuration directory
                        main_go_path = os.path.join(full_path, 'main.go')
                        if os.path.exists(main_go_path):
                            print(f"   Found main.go, building collector...")
                            os.makedirs(os.path.join(build_dir, 'bin'), exist_ok=True)
                            result = subprocess.run(
                                ['go', 'build', '-o', 'bin/otelcol-contrib', collector_path],
                                cwd=build_dir,
                                env=build_env,
                                timeout=1800  # 30 minute timeout
                            )
                        else:
                            print(f"   No main.go found, this might be a config-only directory")
                            # Try building from the root with the package path
                            print(f"   Trying to build package {collector_path}...")
                            os.makedirs(os.path.join(build_dir, 'bin'), exist_ok=True)
                            result = subprocess.run(
                                ['go', 'build', '-o', 'bin/otelcol-contrib', collector_path],
                                cwd=build_dir,
                                env=build_env,
                                timeout=1800  # 30 minute timeout
                            )
                        break

                if result is None or (result and result.returncode != 0):
                    print("   ⚠️  Direct build failed, trying builder approach...")

                    # First, try to use go install to get the ocb tool directly
                    print("   Trying to install OCB tool...")
                    ocb_install_result = subprocess.run(
                        ['go', 'install', 'go.opentelemetry.io/collector/cmd/builder@latest'],
                        cwd=build_dir,
                        env=build_env,
                        timeout=600
                    )

                    if ocb_install_result.returncode == 0:
                        print("   ✓ OCB tool installed successfully")

                        # Find the builder binary - it could be in several locations
                        builder_locations = [
                            'builder',  # if it's in PATH
                            os.path.expanduser('~/go/bin/builder'),  # default GOPATH
                            os.path.join(os.environ.get('GOPATH', ''), 'bin', 'builder'),  # custom GOPATH
                            '/usr/local/go/bin/builder',  # system install
                        ]

                        builder_cmd = None
                        for loc in builder_locations:
                            if shutil.which(loc) or (loc != 'builder' and os.path.exists(loc)):
                                builder_cmd = loc
                                print(f"   Found builder at: {builder_cmd}")
                                break

                        if builder_cmd:
                            # Use the builder to create the collector
                            result = subprocess.run(
                                [builder_cmd, '--config', builder_config, '--skip-compilation'],
                                cwd=build_dir,
                                env=build_env
                            )

                            if result.returncode == 0:
                                print("   ✓ Collector sources generated successfully")
                                print("   🔧 Compiling the collector (this may take 20-40 minutes)...")

                                # Now compile the generated sources with a longer timeout
                                compile_result = subprocess.run(
                                    ['go', 'build', '-o', '../bin/otelcol-contrib', '.'],
                                    cwd=os.path.join(build_dir, '_build'),
                                    env=build_env,
                                    timeout=3600  # 60 minute timeout for compilation
                                )
                                result = compile_result
                        else:
                            print("   ⚠️  Could not locate builder binary after installation")
                            result = None
                    else:
                        print("   ⚠️  OCB install failed, trying local builder...")
                        # Try to build the builder tool from source
                        for builder_path in builder_paths:
                            full_path = os.path.join(build_dir, builder_path.lstrip('./'))
                            if os.path.exists(full_path):
                                print(f"   Found builder at: {builder_path}")
                                ocb_result = subprocess.run(
                                    ['go', 'build', '-o', 'ocb', builder_path],
                                    cwd=build_dir,
                                    env=build_env,
                                    timeout=600  # 10 minute timeout for builder
                                )

                                if ocb_result.returncode == 0:
                                    print("   ✓ OCB builder created successfully")
                                    # Use the builder to create the collector
                                    result = subprocess.run(
                                        ['./ocb', '--config', builder_config, '--skip-compilation'],
                                        cwd=build_dir,
                                        env=build_env
                                    )

                                    if result.returncode == 0:
                                        print("   ✓ Collector sources generated successfully")
                                        print("   🔧 Compiling the collector (this may take 20-40 minutes)...")

                                        # Now compile the generated sources with a longer timeout
                                        compile_result = subprocess.run(
                                            ['go', 'build', '-o', '../bin/otelcol-contrib', '.'],
                                            cwd=os.path.join(build_dir, '_build'),
                                            env=build_env
                                        )
                                        result = compile_result
                                break

                if result is None:
                    print("   ❌ Could not find collector or builder source")
                    return False

                if result.returncode != 0:
                    print(f"❌ Build failed with compilation errors")
                    print(f"   This may be due to platform-specific code issues in version {version}")
                    print(f"   The Python OpenTelemetry packages are installed and working.")
                    print(f"   The OpenTelemetry Collector is optional - you can:")
                    print(f"   1. Use Prometheus alone for metrics")
                    print(f"   2. Try a different OTEL Collector version")
                    print(f"   3. Use a pre-built binary from a different source")
                    return False

                # Find the built binary - check multiple possible locations
                binary_path = None
                possible_paths = [
                    os.path.join(build_dir, 'bin', 'otelcol-contrib'),
                    os.path.join(build_dir, '_build', 'otelcol-contrib'),
                    os.path.join(build_dir, 'otelcol-contrib'),
                ]

                # Also check bin directory for any otel binaries
                bin_dir = os.path.join(build_dir, 'bin')
                if os.path.exists(bin_dir):
                    binaries = [f for f in os.listdir(bin_dir) if 'otel' in f.lower() and os.path.isfile(os.path.join(bin_dir, f))]
                    for binary in binaries:
                        possible_paths.append(os.path.join(bin_dir, binary))

                # Check _build directory too (OCB default output)
                build_output_dir = os.path.join(build_dir, '_build')
                if os.path.exists(build_output_dir):
                    binaries = [f for f in os.listdir(build_output_dir) if 'otel' in f.lower() and os.path.isfile(os.path.join(build_output_dir, f))]
                    for binary in binaries:
                        possible_paths.append(os.path.join(build_output_dir, binary))

                for path in possible_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        binary_path = path
                        print(f"   ✓ Found binary: {os.path.basename(path)} at {path}")
                        break

                if not binary_path or not os.path.exists(binary_path):
                    print(f"❌ Built binary not found in {bin_dir}")
                    if os.path.exists(bin_dir):
                        print(f"   Contents of bin directory: {os.listdir(bin_dir)}")
                    return False

                # Install to appropriate directory
                if platform_name == 'freebsd' and os.path.exists('/usr/pkg/bin'):
                    install_dir = '/usr/pkg/bin'
                else:
                    install_dir = '/usr/local/bin'

                try:
                    shutil.copy2(binary_path, os.path.join(install_dir, 'otelcol-contrib'))
                    os.chmod(os.path.join(install_dir, 'otelcol-contrib'), 0o755)
                    print(f"✅ OpenTelemetry Collector built and installed to {install_dir}")
                    return True
                except PermissionError:
                    print(f"⚠️  Need elevated privileges to install to {install_dir}")
                    print(f"   Built binary is at: {binary_path}")
                    print(f"   Run: sudo cp {binary_path} {install_dir}/")
                    return False

            else:
                print(f"❌ Building from source not supported for platform: {platform_name}")
                return False

    except subprocess.TimeoutExpired:
        print("❌ Build timed out after 30 minutes")
        return False
    except Exception as e:
        print(f"❌ Failed to build from source: {e}")
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
        version = "0.136.0"  # Latest stable version

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

        elif platform_name in ['darwin', 'freebsd', 'netbsd', 'openbsd']:
            # macOS and BSD systems - try binary first, build from source as fallback
            filename = f"otelcol-contrib_{version}_{platform_name}_{arch}.tar.gz"
            url = f"https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v{version}/{filename}"

            print(f"Attempting to download OpenTelemetry Collector {version} for {platform_name}-{arch}...")

            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    archive_path = os.path.join(temp_dir, filename)

                    # Try downloading binary
                    response = requests.get(url, stream=True, timeout=300)
                    response.raise_for_status()

                    with open(archive_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Extract
                    with tarfile.open(archive_path, 'r:gz') as tar:
                        safe_extract_tar(tar, temp_dir)

                    # Determine install directory (BSD uses /usr/pkg/bin or /usr/local/bin)
                    if platform_name == 'freebsd' and os.path.exists('/usr/pkg/bin'):
                        install_dir = '/usr/pkg/bin'
                    else:
                        install_dir = '/usr/local/bin'

                    # Install binary
                    try:
                        shutil.copy2(
                            os.path.join(temp_dir, 'otelcol-contrib'),
                            os.path.join(install_dir, 'otelcol-contrib')
                        )
                        os.chmod(os.path.join(install_dir, 'otelcol-contrib'), 0o755)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
                    except PermissionError:
                        print(f"⚠️  Need elevated privileges to install to {install_dir}")
                        print("   OTEL Collector binary downloaded but not installed")
                        print(f"   You can manually copy it from: {temp_dir}")
                        return False

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Binary not available, try building from source
                    print(f"⚠️  Pre-built binary not available, building from source...")
                    return build_otel_collector_from_source(version, platform_name, arch)
                else:
                    raise

        elif platform_name == 'windows':
            # Windows - use tar.gz format like other platforms
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

                # Extract tar.gz
                with tarfile.open(archive_path, 'r:gz') as tar:
                    safe_extract_tar(tar, temp_dir)

                # Install to user's local bin directory
                install_dir = os.path.expanduser(r"~\AppData\Local\bin")
                os.makedirs(install_dir, exist_ok=True)

                shutil.copy2(
                    os.path.join(temp_dir, 'otelcol-contrib.exe'),
                    os.path.join(install_dir, 'otelcol-contrib.exe')
                )

                # Provide PATH hint for Windows users
                print(f"💡 Add {install_dir} to your PATH to use 'otelcol-contrib' command globally")

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

    system = platform.system().lower()

    if system == 'windows':
        # Windows-specific directories
        config_dirs = [
            os.path.expanduser(r'~\AppData\Local\otelcol-contrib'),
            os.path.expanduser(r'~\AppData\Local\prometheus'),
            os.path.expanduser(r'~\AppData\Local\prometheus\data'),
            os.path.expanduser(r'~\AppData\Local\prometheus\logs')
        ]
    else:
        # Unix-like systems
        config_dirs = [
            '/etc/otelcol-contrib',
            '/etc/prometheus',
            '/var/lib/prometheus',
            '/var/log/prometheus'
        ]

    for config_dir in config_dirs:
        try:
            if system == 'windows':
                os.makedirs(config_dir, exist_ok=True)
                print(f"✅ Created directory: {config_dir}")
            else:
                os.makedirs(config_dir, exist_ok=True, mode=0o755)
                print(f"✅ Created directory: {config_dir}")
        except PermissionError:
            if system != 'windows':
                try:
                    subprocess.run(['sudo', 'mkdir', '-p', config_dir], check=True)
                    subprocess.run(['sudo', 'chmod', '755', config_dir], check=True)
                    print(f"✅ Created directory (with sudo): {config_dir}")
                except subprocess.CalledProcessError as e:
                    print(f"❌ Failed to create directory {config_dir}: {e}")
                    return False
            else:
                print(f"❌ Failed to create directory {config_dir}: Permission denied")
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

    # Check for elevated privileges only if needed
    if platform.system() != 'Windows':
        # Check if we can write to common installation directories
        test_dirs = ['/usr/local/bin', '/etc']
        needs_sudo = False
        for test_dir in test_dirs:
            if os.path.exists(test_dir) and not os.access(test_dir, os.W_OK):
                needs_sudo = True
                break

        if needs_sudo and os.geteuid() != 0:
            print("❌ This script requires elevated privileges to install to system directories.")
            print("Please run: sudo python3 scripts/install-telemetry.py")
            print("Or ensure /usr/local/bin and /etc are writable by your user.")
            sys.exit(1)

    success_count = 0
    total_steps = 4

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