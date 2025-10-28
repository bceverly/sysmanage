# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test test-python test-vite test-playwright test-performance lint lint-python lint-typescript security security-full security-python security-frontend security-secrets security-upgrades clean build setup install-dev migrate help start stop start-openbao stop-openbao status-openbao start-telemetry stop-telemetry status-telemetry installer installer-deb sbom

# Default target
help:
	@echo "SysManage Server - Available targets:"
	@echo "  make start         - Start SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make stop          - Stop SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make test          - Run all tests (Python + TypeScript + UI integration + Performance)"
	@echo "  make test-python   - Run Python backend tests only"
	@echo "  make test-vite     - Run Vite/TypeScript frontend tests only"
	@echo "  make test-playwright - Run Playwright UI tests only"
	@echo "  make test-performance - Run Artillery load tests and Playwright performance tests"
	@echo "  make lint          - Run all linters (Python + TypeScript)"
	@echo "  make lint-python   - Run Python linting only"
	@echo "  make lint-typescript - Run TypeScript linting only"
	@echo "  make security      - Run comprehensive security analysis (all tools)"
	@echo "  make security-full - Run comprehensive security analysis (all tools)"
	@echo "  make security-python - Run Python security scanning (Bandit + Safety)"
	@echo "  make security-frontend - Run frontend security scanning (ESLint)"
	@echo "  make security-secrets - Run secrets detection"
	@echo "  make security-upgrades - Check for security package upgrades"
	@echo "  make setup         - Install development dependencies"
	@echo "  make clean         - Clean test artifacts and cache"
	@echo "  make build         - Build frontend for production"
	@echo "  make install-dev   - Install all development tools (includes Playwright + WebDriver + MSW for testing)"
	@echo "  make migrate       - Run database migrations (alembic upgrade head)"
	@echo "  make check-test-models - Check test model synchronization between conftest files"
	@echo ""
	@echo "Packaging targets:"
	@echo "  make installer         - Build installer package (auto-detects platform)"
	@echo "  make installer-deb     - Build Ubuntu/Debian .deb package (explicit)"
	@echo "  make installer-rpm-centos - Build CentOS/RHEL/Fedora .rpm package (explicit)"
	@echo "  make installer-rpm-opensuse - Build OpenSUSE/SLES .rpm package with vendor deps (explicit)"
	@echo "  make installer-openbsd - Build OpenBSD port tarball (explicit)"
	@echo "  make sbom              - Generate Software Bill of Materials (CycloneDX format)"
	@echo ""
	@echo "OpenBAO (Vault) targets:"
	@echo "  make start-openbao - Start OpenBAO development server only"
	@echo "  make stop-openbao  - Stop OpenBAO development server only"
	@echo "  make status-openbao - Check OpenBAO server status"
	@echo ""
	@echo "Telemetry/Observability targets:"
	@echo "  make status-telemetry  - Check telemetry services status"
	@echo "  Note: Telemetry services are automatically started/stopped with 'make start/stop'"
	@echo "  Note: Telemetry stack is automatically installed with 'make install-dev'"
	@echo ""
	@echo "BSD users: install-dev will check for C tracer dependencies"
	@echo "  - OpenBSD: gcc-11.2.0p15, findutils (builds cffi, grpcio from source)"
	@echo "  - NetBSD: gcc13, py312-cffi"

# Virtual environment activation
VENV := .venv

# Detect OS and set paths accordingly
ifeq ($(OS),Windows_NT)
    PYTHON := python
    PIP := pip
    VENV_ACTIVATE := $(VENV)/Scripts/activate
else
    PYTHON := $(VENV)/bin/python
    PIP := $(VENV)/bin/pip
    VENV_ACTIVATE := $(VENV)/bin/activate
endif

# Create or repair virtual environment
$(VENV_ACTIVATE):
	@echo "Creating/repairing virtual environment..."
ifeq ($(OS),Windows_NT)
	@if exist $(VENV) rmdir /s /q $(VENV) 2>nul || echo.
	@python -m venv $(VENV)
	@$(PYTHON) -m pip install --upgrade pip
else
	@rm -rf $(VENV) 2>/dev/null || true
	@if command -v python3 >/dev/null 2>&1; then \
		python3 -m venv $(VENV); \
	elif command -v python3.12 >/dev/null 2>&1; then \
		python3.12 -m venv $(VENV); \
	elif command -v python3.11 >/dev/null 2>&1; then \
		python3.11 -m venv $(VENV); \
	else \
		echo "Error: No Python 3 found"; exit 1; \
	fi
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		export TMPDIR=$$HOME/tmp && $(PYTHON) -m pip install --upgrade pip; \
	else \
		$(PYTHON) -m pip install --upgrade pip; \
	fi
endif

setup-venv: $(VENV_ACTIVATE)

# Install development dependencies
install-dev: setup-venv
	@echo "Installing Python development dependencies..."
ifeq ($(OS),Windows_NT)
	@$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep
else
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "[INFO] OpenBSD detected - using ~/tmp for builds..."; \
		export TMPDIR=$$HOME/tmp && \
		$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep; \
	elif [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD detected - configuring for grpcio build..."; \
		export TMPDIR=/var/tmp && \
		export CC=/usr/pkg/gcc14/bin/gcc && \
		export CXX=/usr/pkg/gcc14/bin/g++ && \
		export CFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" && \
		export CXXFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" && \
		export LDFLAGS="-L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib -lstdc++" && \
		export LDSHARED="/usr/pkg/gcc14/bin/g++ -pthread -shared -L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib" && \
		export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
		export GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1 && \
		$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep; \
	else \
		$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep; \
	fi
endif
	@echo "Installing requirements.txt (includes Selenium WebDriver)..."
ifeq ($(OS),Windows_NT)
	@$(PYTHON) -m pip install -r requirements.txt
else
	@if [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD - using /var/tmp and excluding Playwright..."; \
		export TMPDIR=/var/tmp && \
		export CC=/usr/pkg/gcc14/bin/gcc && \
		export CXX=/usr/pkg/gcc14/bin/g++ && \
		export CFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" && \
		export CXXFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" && \
		export LDFLAGS="-L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib -lstdc++" && \
		export LDSHARED="/usr/pkg/gcc14/bin/g++ -pthread -shared -L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib" && \
		export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
		export GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1 && \
		grep -v "playwright" requirements.txt | $(PYTHON) -m pip install -r /dev/stdin || true; \
		echo "[INFO] Selenium will be used for browser testing on BSD systems"; \
	elif [ "$$(uname -s)" = "FreeBSD" ]; then \
		echo "[INFO] Installing packages except Playwright (not available on BSD systems)..."; \
		grep -v "playwright" requirements.txt | $(PYTHON) -m pip install -r /dev/stdin || true; \
		echo "[INFO] Selenium will be used for browser testing on BSD systems"; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "[INFO] OpenBSD - patching and building grpcio with bundled abseil..."; \
		export TMPDIR=$$HOME/tmp && \
		$(MAKE) build-grpcio-openbsd || { echo "[ERROR] grpcio build failed - see ~/tmp/grpcio-build.log"; exit 1; }; \
		echo "[INFO] Now installing remaining dependencies..."; \
		export TMPDIR=$$HOME/tmp && \
		grep -v "playwright" requirements.txt | $(PYTHON) -m pip install -r /dev/stdin || { echo "[ERROR] Failed to install requirements"; exit 1; }; \
		echo "[INFO] Selenium will be used for browser testing on BSD systems"; \
	else \
		$(PYTHON) -m pip install -r requirements.txt; \
	fi
endif
	@echo "Checking for BSD system C tracer requirements..."
	@$(PYTHON) scripts/check-bsd-deps.py
ifeq ($(OS),Windows_NT)
	@echo "[INFO] Windows detected - skipping BSD-specific package builds"
else
	@if [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD detected - rebuilding Pillow with correct library paths..."; \
		export TMPDIR=/var/tmp && \
		export CFLAGS="-I/usr/pkg/include" && \
		export CXXFLAGS="-I/usr/pkg/include" && \
		export LDFLAGS="-L/usr/pkg/lib -Wl,-rpath,/usr/pkg/lib" && \
		$(PYTHON) -m pip uninstall -y Pillow && $(PYTHON) -m pip install --no-binary=:all: Pillow; \
		echo "[OK] Pillow rebuilt for NetBSD"; \
		echo "[INFO] NetBSD detected - rebuilding grpcio with GCC 14 for C++ compatibility..."; \
		$(PYTHON) -m pip cache remove grpcio 2>/dev/null || true; \
		$(PYTHON) -m pip uninstall -y grpcio && \
		TMPDIR=/var/tmp \
		CC=/usr/pkg/gcc14/bin/gcc \
		CXX=/usr/pkg/gcc14/bin/g++ \
		CFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
		CXXFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
		LDFLAGS="-L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib -lstdc++" \
		LDSHARED="/usr/pkg/gcc14/bin/g++ -pthread -shared -L/usr/pkg/gcc14/lib -Wl,-rpath,/usr/pkg/gcc14/lib" \
		GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 \
		GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 \
		GRPC_PYTHON_BUILD_SYSTEM_CARES=1 \
		GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1 \
		$(PYTHON) -m pip install --no-binary=:all: --no-cache-dir grpcio; \
		echo "[OK] grpcio rebuilt for NetBSD with GCC 14"; \
		echo "[INFO] Setting up GCC 14 library path in venv activate script..."; \
		if [ ! -f "$(VENV)/bin/activate.backup" ]; then \
			cp "$(VENV)/bin/activate" "$(VENV)/bin/activate.backup"; \
		fi; \
		grep -q "LD_LIBRARY_PATH.*gcc14" "$(VENV)/bin/activate" || \
		echo 'export LD_LIBRARY_PATH="/usr/pkg/gcc14/lib:$${LD_LIBRARY_PATH}"' >> "$(VENV)/bin/activate"; \
		echo "[OK] GCC 14 library path configured in venv"; \
		echo "[INFO] NetBSD detected - fixing websocket dependencies for Selenium compatibility..."; \
		$(PYTHON) -m pip uninstall -y websocket 2>/dev/null || true; \
		rm -rf $(VENV_DIR)/lib/python*/site-packages/websocket $(VENV_DIR)/lib/python*/site-packages/websocket-*.dist-info 2>/dev/null || true; \
		$(PYTHON) -m pip install --force-reinstall websocket-client websockets; \
		echo "[OK] websocket dependencies fixed for NetBSD Selenium support"; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "[INFO] OpenBSD detected - fixing websocket dependencies for Selenium compatibility..."; \
		$(PYTHON) -m pip uninstall -y websocket 2>/dev/null || true; \
		rm -rf $(VENV_DIR)/lib/python*/site-packages/websocket $(VENV_DIR)/lib/python*/site-packages/websocket-*.dist-info 2>/dev/null || true; \
		export TMPDIR=$$HOME/tmp && $(PYTHON) -m pip install --force-reinstall websocket-client websockets; \
		echo "[OK] websocket dependencies fixed for OpenBSD Selenium support"; \
	fi
endif
	@echo "Installing OpenBAO for secrets management..."
	@$(PYTHON) scripts/install-openbao.py
ifeq ($(OS),Windows_NT)
	@echo "Installing telemetry stack (OpenTelemetry + Prometheus)..."
	@$(PYTHON) scripts/install-telemetry.py || echo "[WARNING] Telemetry installation failed - continuing without telemetry"
else
	@if [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD detected - building Prometheus from source..."; \
		if [ ! -f "$$HOME/.local/bin/prometheus" ]; then \
			mkdir -p /tmp/prometheus-build && \
			cd /tmp/prometheus-build && \
			rm -rf prometheus && \
			git clone --depth 1 --branch v3.1.0 https://github.com/prometheus/prometheus.git && \
			cd prometheus && \
			echo "[INFO] Building Prometheus (this may take several minutes)..." && \
			go build ./cmd/prometheus && \
			go build ./cmd/promtool && \
			mkdir -p $$HOME/.local/bin && \
			cp prometheus promtool $$HOME/.local/bin/ && \
			chmod +x $$HOME/.local/bin/prometheus $$HOME/.local/bin/promtool && \
			cd /tmp && rm -rf /tmp/prometheus-build && \
			echo "[OK] Prometheus built and installed to ~/.local/bin"; \
		else \
			echo "[OK] Prometheus already installed"; \
		fi; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "[INFO] OpenBSD detected - building Prometheus from source..."; \
		if [ ! -f "$$HOME/.local/bin/prometheus" ]; then \
			mkdir -p $$HOME/tmp/prometheus-build && \
			export GOCACHE=$$HOME/tmp/go-cache && \
			export GOMODCACHE=$$HOME/tmp/go-mod-cache && \
			export GOTMPDIR=$$HOME/tmp/go-tmp && \
			mkdir -p $$HOME/tmp/go-cache $$HOME/tmp/go-mod-cache $$HOME/tmp/go-tmp && \
			cd $$HOME/tmp/prometheus-build && \
			rm -rf prometheus && \
			git clone --depth 1 --branch v3.1.0 https://github.com/prometheus/prometheus.git && \
			cd prometheus && \
			echo "[INFO] Building Prometheus (this may take several minutes)..." && \
			go build ./cmd/prometheus && \
			go build ./cmd/promtool && \
			mkdir -p $$HOME/.local/bin && \
			cp prometheus promtool $$HOME/.local/bin/ && \
			chmod +x $$HOME/.local/bin/prometheus $$HOME/.local/bin/promtool && \
			cd $$HOME && rm -rf $$HOME/tmp/prometheus-build && \
			echo "[OK] Prometheus built and installed to ~/.local/bin"; \
		else \
			echo "[OK] Prometheus already installed"; \
		fi; \
	fi
	@echo "Installing telemetry stack (OpenTelemetry + Prometheus)..."
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		doas $(PYTHON) scripts/install-telemetry.py || echo "[WARNING] Telemetry installation failed - continuing without telemetry"; \
	else \
		sudo -H $(PYTHON) scripts/install-telemetry.py || echo "[WARNING] Telemetry installation failed - continuing without telemetry"; \
	fi
endif
	@echo "Setting up WebDriver for screenshots..."
	@$(PYTHON) scripts/install-browsers.py
ifeq ($(OS),Windows_NT)
	@echo "Installing Playwright browsers for Windows..."
	@$(PYTHON) -m playwright install chromium firefox webkit 2>nul || echo "Playwright browser installation failed - continuing with Selenium fallback"
else
	@if [ "$$(uname -s)" != "OpenBSD" ] && [ "$$(uname -s)" != "FreeBSD" ] && [ "$$(uname -s)" != "NetBSD" ]; then \
		echo "Installing Playwright browsers for Unix-like system..."; \
		$(PYTHON) -m playwright install chromium firefox webkit 2>/dev/null || echo "Playwright browser installation failed - continuing with Selenium fallback"; \
		echo "Checking Playwright browser dependencies..."; \
		$(PYTHON) -c "from playwright.sync_api import sync_playwright; exec('with sync_playwright() as p: browser = p.chromium.launch(headless=True); browser.close(); print(\"✓ Playwright dependencies working\")')" 2>/dev/null || ( \
			echo "Installing Playwright system dependencies..."; \
			echo "This may prompt for sudo password to install system packages..."; \
			if command -v sudo >/dev/null 2>&1; then \
				sudo -H $(PYTHON) -m playwright install-deps 2>/dev/null || ( \
					echo ""; \
					echo "❌ Playwright automatic dependency installation failed."; \
					echo "   Installing manually..."; \
					echo ""; \
					sudo -H apt-get update -qq && \
					sudo -H apt-get install -y \
						libicu76 libavif16 libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 \
						libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 libdrm2 libgbm1 \
						libglib2.0-0t64 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 \
						libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
						libcairo-gobject2 libfontconfig1 libfreetype6 libgdk-pixbuf-2.0-0 \
						libgtk-3-0t64 libpangocairo-1.0-0 libx11-xcb1 libxcb-shm0 libxcursor1 \
						libxi6 libxrender1 fonts-liberation xvfb && \
					echo "✓ Comprehensive dependency installation completed" \
				); \
			else \
				echo "❌ sudo not available and Playwright dependencies needed manual installation"; \
			fi \
		); \
	else \
		echo "BSD system detected - skipping Playwright browser installation (using Selenium)"; \
	fi
endif
	@echo "Installing TypeScript/React development dependencies..."
ifeq ($(OS),Windows_NT)
	@cd frontend && npm install --include=optional
else
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		mkdir -p $$HOME/.npm-cache && \
		cd frontend && npm install --include=optional --cache=$$HOME/.npm-cache; \
	else \
		cd frontend && npm install --include=optional; \
	fi
endif
	@echo "Ensuring esbuild optional dependencies are installed..."
ifeq ($(OS),Windows_NT)
	@cd frontend && npm uninstall esbuild && npm install esbuild
else
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		cd frontend && npm uninstall esbuild && npm install esbuild --cache=$$HOME/.npm-cache; \
	else \
		cd frontend && npm uninstall esbuild && npm install esbuild; \
	fi
endif
	@echo "Installing packaging/installer build tools for your platform..."
ifeq ($(OS),Windows_NT)
	@echo "[INFO] Windows detected - checking for WiX Toolset..."
	@where wix >nul 2>&1 && echo "✓ WiX Toolset already installed" || ( \
		echo "[WARNING] WiX Toolset not found. Please install manually:" && \
		echo "  Download from: https://wixtoolset.org/releases/" && \
		echo "  Or via winget: winget install --id=WiXToolset.WiX -e" \
	)
else
	@if [ -f /etc/redhat-release ]; then \
		echo "[INFO] Red Hat-based system detected - checking for RPM build tools..."; \
		MISSING_PKGS=""; \
		command -v rpmbuild >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpm-build"; \
		command -v rpmdev-setuptree >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpmdevtools"; \
		rpm -q python3-devel >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python3-devel"; \
		rpm -q python3-setuptools >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python3-setuptools"; \
		rpm -q nodejs >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS nodejs"; \
		if [ -n "$$MISSING_PKGS" ]; then \
			echo "Missing packages:$$MISSING_PKGS"; \
			echo "Installing RPM build tools..."; \
			if command -v dnf >/dev/null 2>&1; then \
				echo "Running: sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync"; \
				sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync || \
				echo "[WARNING] Could not install RPM build tools. Run manually: sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync"; \
			else \
				echo "Running: sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync"; \
				sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync || \
				echo "[WARNING] Could not install RPM build tools. Run manually: sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools nodejs rsync"; \
			fi; \
		else \
			echo "✓ All RPM build tools already installed"; \
		fi; \
		echo "[INFO] Checking for Flatpak build tools..."; \
		MISSING_FLATPAK=""; \
		if ! command -v flatpak >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak"; \
		fi; \
		if ! command -v flatpak-builder >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak-builder"; \
		fi; \
		if [ -n "$$MISSING_FLATPAK" ]; then \
			echo "Missing Flatpak tools:$$MISSING_FLATPAK"; \
			echo "Installing Flatpak build tools..."; \
			if command -v dnf >/dev/null 2>&1; then \
				echo "Running: sudo dnf install -y flatpak flatpak-builder"; \
				sudo dnf install -y flatpak flatpak-builder || { \
					echo "[WARNING] Could not install Flatpak tools. Run manually: sudo dnf install -y flatpak flatpak-builder"; \
				}; \
			else \
				echo "Running: sudo yum install -y flatpak flatpak-builder"; \
				sudo yum install -y flatpak flatpak-builder || { \
					echo "[WARNING] Could not install Flatpak tools. Run manually: sudo yum install -y flatpak flatpak-builder"; \
				}; \
			fi; \
		else \
			echo "✓ Flatpak build tools already installed"; \
		fi; \
		if command -v flatpak >/dev/null 2>&1; then \
			if ! flatpak remote-list --user | grep -q flathub; then \
				echo "Adding Flathub repository (user)..."; \
				flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo || { \
					echo "[WARNING] Could not add Flathub repository"; \
				}; \
			else \
				echo "✓ Flathub repository already configured (user)"; \
			fi; \
		fi; \
	elif [ -f /etc/os-release ] && grep -qE "^ID=\"?(opensuse-leap|opensuse-tumbleweed|sles)\"?" /etc/os-release; then \
		echo "[INFO] openSUSE/SLES detected - checking for RPM build tools..."; \
		MISSING_PKGS=""; \
		command -v rpmbuild >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpm-build"; \
		command -v rpmdev-setuptree >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpmdevtools"; \
		rpm -q python311-devel >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python311-devel"; \
		rpm -q python3-setuptools >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python3-setuptools"; \
		rpm -q nodejs >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS nodejs"; \
		if [ -n "$$MISSING_PKGS" ]; then \
			echo "Missing packages:$$MISSING_PKGS"; \
			echo "Installing RPM build tools..."; \
			echo "Running: sudo zypper install -y rpm-build rpmdevtools python311-devel python3-setuptools nodejs rsync"; \
			sudo zypper install -y rpm-build rpmdevtools python311-devel python3-setuptools nodejs rsync || \
			echo "[WARNING] Could not install RPM build tools. Run manually: sudo zypper install -y rpm-build rpmdevtools python311-devel python3-setuptools nodejs rsync"; \
		else \
			echo "✓ All RPM build tools already installed"; \
		fi; \
		echo "[INFO] Checking for Flatpak build tools..."; \
		MISSING_FLATPAK=""; \
		if ! command -v flatpak >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak"; \
		fi; \
		if ! command -v flatpak-builder >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak-builder"; \
		fi; \
		if [ -n "$$MISSING_FLATPAK" ]; then \
			echo "Missing Flatpak tools:$$MISSING_FLATPAK"; \
			echo "Installing Flatpak build tools..."; \
			echo "Running: sudo zypper install -y flatpak flatpak-builder"; \
			sudo zypper install -y flatpak flatpak-builder || { \
				echo "[WARNING] Could not install Flatpak tools. Run manually: sudo zypper install -y flatpak flatpak-builder"; \
			}; \
		else \
			echo "✓ Flatpak build tools already installed"; \
		fi; \
		if command -v flatpak >/dev/null 2>&1; then \
			if ! flatpak remote-list --user | grep -q flathub; then \
				echo "Adding Flathub repository (user)..."; \
				flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo || { \
					echo "[WARNING] Could not add Flathub repository"; \
				}; \
			else \
				echo "✓ Flathub repository already configured (user)"; \
			fi; \
		fi; \
	elif [ "$$(uname -s)" = "Linux" ] && [ -f /etc/lsb-release ] && grep -q Ubuntu /etc/lsb-release 2>/dev/null; then \
		echo "[INFO] Ubuntu/Debian detected - checking for packaging build tools..."; \
		MISSING_PKGS=""; \
		command -v dpkg-buildpackage >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS devscripts"; \
		dpkg -l dh-python 2>/dev/null | grep -q "^ii" || MISSING_PKGS="$$MISSING_PKGS dh-python"; \
		dpkg -l python3-all 2>/dev/null | grep -q "^ii" || MISSING_PKGS="$$MISSING_PKGS python3-all"; \
		dpkg -l debhelper 2>/dev/null | grep -q "^ii" || MISSING_PKGS="$$MISSING_PKGS debhelper"; \
		dpkg -l lintian 2>/dev/null | grep -q "^ii" || MISSING_PKGS="$$MISSING_PKGS lintian"; \
		if [ -n "$$MISSING_PKGS" ]; then \
			echo "Missing packages:$$MISSING_PKGS"; \
			echo "Installing Debian packaging build tools..."; \
			echo "Running: sudo apt-get install -y debhelper dh-python python3-all python3-setuptools build-essential devscripts lintian nodejs npm"; \
			sudo apt-get update && sudo apt-get install -y debhelper dh-python python3-all python3-setuptools build-essential devscripts lintian nodejs npm || \
			echo "[WARNING] Could not install packaging tools. Run manually: sudo apt-get install -y debhelper dh-python python3-all python3-setuptools build-essential devscripts lintian nodejs npm"; \
		else \
			echo "✓ All packaging build tools already installed"; \
		fi; \
		echo "[INFO] Checking for Snap build tools..."; \
		if ! command -v snap >/dev/null 2>&1; then \
			echo "snapd not found - installing..."; \
			echo "Running: sudo apt-get install -y snapd"; \
			sudo apt-get install -y snapd || { \
				echo "[WARNING] Could not install snapd. Run manually: sudo apt-get install -y snapd"; \
			}; \
			echo "Ensuring snapd service is enabled and started..."; \
			sudo systemctl enable --now snapd.socket || true; \
			sudo systemctl start snapd || true; \
			echo "Waiting for snapd to initialize..."; \
			sleep 5; \
		fi; \
		if ! snap list 2>/dev/null | grep -q snapcraft; then \
			echo "snapcraft not found - installing..."; \
			echo "Running: sudo snap install snapcraft --classic"; \
			sudo snap install snapcraft --classic || { \
				echo "[WARNING] Could not install snapcraft. Run manually: sudo snap install snapcraft --classic"; \
			}; \
		else \
			echo "✓ snapcraft already installed"; \
		fi; \
		echo "[INFO] Checking for Flatpak build tools..."; \
		MISSING_FLATPAK=""; \
		if ! command -v flatpak >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak"; \
		fi; \
		if ! command -v flatpak-builder >/dev/null 2>&1; then \
			MISSING_FLATPAK="$$MISSING_FLATPAK flatpak-builder"; \
		fi; \
		if [ -n "$$MISSING_FLATPAK" ]; then \
			echo "Missing Flatpak tools:$$MISSING_FLATPAK"; \
			echo "Installing Flatpak build tools..."; \
			echo "Running: sudo apt-get install -y flatpak flatpak-builder"; \
			sudo apt-get install -y flatpak flatpak-builder || { \
				echo "[WARNING] Could not install Flatpak tools. Run manually: sudo apt-get install -y flatpak flatpak-builder"; \
			}; \
		else \
			echo "✓ Flatpak build tools already installed"; \
		fi; \
		if command -v flatpak >/dev/null 2>&1; then \
			if ! flatpak remote-list --user | grep -q flathub; then \
				echo "Adding Flathub repository (user)..."; \
				flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo || { \
					echo "[WARNING] Could not add Flathub repository"; \
				}; \
			else \
				echo "✓ Flathub repository already configured (user)"; \
			fi; \
		fi; \
	elif [ "$$(uname -s)" = "FreeBSD" ]; then \
		echo "[INFO] FreeBSD detected - checking for packaging tools..."; \
		if ! command -v pkgconf >/dev/null 2>&1; then \
			echo "pkgconf not found - installing..."; \
			echo "Running: sudo pkg install -y pkgconf"; \
			sudo pkg install -y pkgconf || { \
				echo "[WARNING] Could not install pkgconf. Run manually: sudo pkg install -y pkgconf"; \
			}; \
		else \
			echo "✓ pkgconf already installed"; \
		fi; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "[INFO] OpenBSD detected - package building uses standard ports system"; \
		echo "      No additional tools needed beyond base system"; \
	elif [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD detected - package building uses pkg_create (in base)"; \
		echo "      No additional tools needed beyond base system"; \
	elif [ -f /etc/redhat-release ]; then \
		echo "[INFO] Red Hat-based system detected - checking for RPM build tools..."; \
		MISSING_PKGS=""; \
		command -v rpmbuild >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpm-build"; \
		command -v rpmdev-setuptree >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS rpmdevtools"; \
		rpm -q python3-devel >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python3-devel"; \
		rpm -q python3-setuptools >/dev/null 2>&1 || MISSING_PKGS="$$MISSING_PKGS python3-setuptools"; \
		if [ -n "$$MISSING_PKGS" ]; then \
			echo "Missing packages:$$MISSING_PKGS"; \
			echo "Installing RPM build tools..."; \
			if command -v dnf >/dev/null 2>&1; then \
				echo "Running: sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync"; \
				sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync || \
				echo "[WARNING] Could not install RPM build tools. Run manually: sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync"; \
			else \
				echo "Running: sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync"; \
				sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync || \
				echo "[WARNING] Could not install RPM build tools. Run manually: sudo yum install -y rpm-build rpmdevtools python3-devel python3-setuptools rsync"; \
			fi; \
		else \
			echo "✓ RPM build tools already installed"; \
		fi; \
	fi
endif
	@echo "Installing ESLint security plugins..."
ifeq ($(OS),Windows_NT)
	@cd frontend && npm install eslint-plugin-security eslint-plugin-no-unsanitized
else
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		cd frontend && npm install eslint-plugin-security eslint-plugin-no-unsanitized --cache=$$HOME/.npm-cache; \
	else \
		cd frontend && npm install eslint-plugin-security eslint-plugin-no-unsanitized; \
	fi
endif
	@echo "Setting up MSW (Mock Service Worker) for API mocking..."
ifeq ($(OS),Windows_NT)
	@cd frontend && npm install --save-dev msw
else
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		cd frontend && npm install --save-dev msw --cache=$$HOME/.npm-cache; \
	else \
		cd frontend && npm install --save-dev msw; \
	fi
endif
	@echo "Initializing MSW browser setup (for optional development use)..."
	@cd frontend && npx msw init public/ --save
	@echo "Running database migrations to ensure tables exist..."
	@$(PYTHON) -m alembic upgrade head || echo "Database migration failed - you may need to configure the database first"
ifeq ($(OS),Windows_NT)
	@echo "Checking for grep installation on Windows..."
	@where grep >nul 2>nul || echo "Note: grep not found. You may want to install it via chocolatey: choco install grep"
endif
ifeq ($(OS),Windows_NT)
	@where eslint >nul 2>nul || (echo "Installing global ESLint..." && npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin)
else
	@if ! command -v eslint >/dev/null 2>&1; then \
		echo "Installing global ESLint..."; \
		npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin; \
	fi
endif
ifeq ($(OS),Windows_NT)
	@echo "Installing Artillery for performance testing..."
	@npm install -g artillery@latest || echo "[WARNING] Artillery installation failed - performance tests may not run"
else
	@if [ "$$(uname -s)" != "OpenBSD" ] && [ "$$(uname -s)" != "FreeBSD" ] && [ "$$(uname -s)" != "NetBSD" ]; then \
		echo "Installing Artillery for performance testing..."; \
		npm install -g artillery@latest || echo "[WARNING] Artillery installation failed - performance tests may not run"; \
	else \
		echo "[SKIP] Artillery installation skipped on BSD systems - performance tests not supported"; \
	fi
endif
	@echo "[OK] Development dependencies installation completed"
	@echo "Development environment setup complete!"

# Database migration target
migrate:
	@echo "Running database migrations..."
	@$(PYTHON) -m alembic upgrade head
	@echo "[OK] Database migrations completed"

# Clean trailing whitespace from Python files (cross-platform)
clean-whitespace: $(VENV_ACTIVATE)
	@echo "Cleaning trailing whitespace from Python files..."
	@$(PYTHON) scripts/clean_whitespace.py

# Python linting
lint-python: format-python
	@echo "=== Python Linting ==="
	@echo "Running pylint..."
ifeq ($(OS),Windows_NT)
	-@$(PYTHON) -m pylint backend/ --rcfile=.pylintrc
else
	@$(PYTHON) -m pylint backend/ --rcfile=.pylintrc || true
endif
	@echo "[OK] Python linting completed"

# TypeScript/React linting
lint-typescript:
	@echo "=== TypeScript/React Linting ==="
	@cd frontend && npm run lint
	@echo "[OK] TypeScript linting completed"

# Combined linting
lint: lint-python lint-typescript
	@echo "[OK] All linting completed successfully!"

# Comprehensive security analysis (default)
security: security-full

# Show upgrade recommendations by checking outdated packages
security-upgrades: $(VENV_ACTIVATE)
	@echo "=== Security Upgrade Recommendations ==="
	@echo "Current versions of security-critical packages:"
	@$(PYTHON) -m pip list | grep -E "(cryptography|aiohttp|black|bandit|websockets|PyYAML|SQLAlchemy|alembic|safety|fastapi|starlette|jinja2|python-multipart|setuptools)"
	@echo ""
	@echo "Checking for outdated packages..."
	@$(PYTHON) -m pip list --outdated --format=columns 2>/dev/null | grep -E "(cryptography|aiohttp|black|bandit|websockets|PyYAML|SQLAlchemy|alembic|safety|fastapi|starlette|jinja2|python-multipart|setuptools)" || echo "All security packages are up to date"
	@echo ""
	@echo "For detailed vulnerability info, check:"
	@echo "  https://platform.safetycli.com/codebases/sysmanage/findings?branch=main"

# Comprehensive security analysis - all tools
security-full: security-python security-frontend security-secrets
	@echo "[OK] Comprehensive security analysis completed!"

# Python security analysis (Bandit + Safety)
security-python: $(VENV_ACTIVATE)
	@echo "=== Python Security Analysis ==="
	@echo "Running Bandit static security analysis..."
ifeq ($(OS),Windows_NT)
	-@$(PYTHON) -m bandit -r backend/ -f screen -x backend/tests/
else
	@$(PYTHON) -m bandit -r backend/ -f screen -x backend/tests/ || true
endif
	@echo ""
	@echo "Running Semgrep static analysis..."
	@echo "Tip: Export SEMGREP_APP_TOKEN for access to Pro rules and supply chain analysis"
ifeq ($(OS),Windows_NT)
	-@if defined SEMGREP_APP_TOKEN (semgrep ci) else (semgrep scan --config="p/default" --config="p/security-audit" --config="p/javascript" --config="p/typescript" --config="p/react" --config="p/python" --config="p/django" --config="p/flask" --config="p/owasp-top-ten") || echo "Semgrep scan completed"
else
	@if [ -n "$$SEMGREP_APP_TOKEN" ]; then \
		echo "Using Semgrep CI with supply chain analysis..."; \
		semgrep ci || true; \
	else \
		echo "Using basic Semgrep scan (set SEMGREP_APP_TOKEN for supply chain analysis)..."; \
		semgrep scan --config="p/default" --config="p/security-audit" --config="p/javascript" --config="p/typescript" --config="p/react" --config="p/python" --config="p/django" --config="p/flask" --config="p/owasp-top-ten" || true; \
	fi
endif
	@echo ""
	@echo "Running Safety dependency vulnerability scan..."
ifeq ($(OS),Windows_NT)
	-@$(PYTHON) -m safety scan --output screen || echo "Safety scan completed with issues"
	-@echo ""
	-@echo "=== Current dependency versions (for upgrade reference) ==="
	-@$(PYTHON) -m pip list | grep -E "(cryptography|aiohttp|black|bandit|websockets|PyYAML|SQLAlchemy|alembic|safety|fastapi|starlette|jinja2|python-multipart|setuptools)" || echo "Package list completed"
else
	@$(PYTHON) -m safety scan --output screen || echo "Safety scan completed with issues"
	@echo ""
	@echo "=== Current dependency versions (for upgrade reference) ==="
	@$(PYTHON) -m pip list | grep -E "(cryptography|aiohttp|black|bandit|websockets|PyYAML|SQLAlchemy|alembic|safety|fastapi|starlette|jinja2|python-multipart|setuptools)" || echo "Package list completed"
endif
	@echo ""
	@echo "Note: Check Safety web UI at https://platform.safetycli.com/codebases/sysmanage/findings?branch=main"
	@echo "      for specific version upgrade recommendations when vulnerabilities are found."
	@echo "[OK] Python security analysis completed"

# Frontend security analysis (ESLint security plugins)
security-frontend:
	@echo "=== Frontend Security Analysis ==="
	@echo "Running ESLint security scanning..."
	@cd frontend && npx eslint --config eslint.security.config.js src/ || echo "Frontend security scan completed with warnings"
	@echo "[OK] Frontend security analysis completed"

# Secrets detection (basic pattern matching)
security-secrets:
	@echo "=== Secrets Detection ==="
	@echo "Scanning for potential secrets and credentials..."
ifeq ($(OS),Windows_NT)
	@echo "Checking for common secret patterns..."
	@powershell -Command "Get-ChildItem -Recurse -File -Exclude '*.pyc' | Where-Object { $$_.DirectoryName -notmatch '(\\.git|\\.venv|\\node_modules|\\__pycache__|\\build)' } | Select-String -Pattern '(password|secret|key|token)\s*[:=]\s*[\x27\x22][^\x27\x22\s]{8,}' -AllMatches" || echo "No obvious secrets found in patterns"
	@echo ""
	@echo "Checking for hardcoded API keys..."
	@powershell -Command "Get-ChildItem -Recurse -File -Exclude '*.pyc' | Where-Object { $$_.DirectoryName -notmatch '(\\.git|\\.venv|\\node_modules|\\__pycache__|\\build)' } | Select-String -Pattern '(api_?key|access_?token|auth_?token)\s*[:=]\s*[\x27\x22][A-Za-z0-9+/=]{20,}' -AllMatches" || echo "No obvious API keys found"
	@echo ""
	@echo "Checking for AWS credentials..."
	@powershell -Command "Get-ChildItem -Recurse -File -Exclude '*.pyc' | Where-Object { $$_.DirectoryName -notmatch '(\\.git|\\.venv|\\node_modules|\\__pycache__|\\build)' } | Select-String -Pattern '(AKIA[0-9A-Z]{16}|aws_secret_access_key)' -AllMatches" || echo "No AWS credentials found"
else
	@echo "Checking for common secret patterns..."
	@grep -r -i --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=build --exclude="*.pyc" -E "(password|secret|key|token)\s*[:=]\s*['\"][^'\"\s]{8,}" . || echo "No obvious secrets found in patterns"
	@echo ""
	@echo "Checking for hardcoded API keys..."
	@grep -r -i --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=build --exclude="*.pyc" -E "(api_?key|access_?token|auth_?token)\s*[:=]\s*['\"][A-Za-z0-9+/=]{20,}" . || echo "No obvious API keys found"
	@echo ""
	@echo "Checking for AWS credentials..."
	@grep -r -i --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=build --exclude="*.pyc" -E "(AKIA[0-9A-Z]{16}|aws_secret_access_key)" . || echo "No AWS credentials found"
endif
	@echo "[OK] Basic secrets detection completed"

# Format Python code (helper target)
format-python: $(VENV_ACTIVATE) clean-whitespace
	@echo "Formatting Python code..."
	@$(PYTHON) -m black backend/ tests/

# Python tests
test-python: $(VENV_ACTIVATE) clean-whitespace
	@echo "=== Running Python Tests ==="
	@echo "Cleaning old SQLite test databases..."
ifeq ($(OS),Windows_NT)
	-@del /s /q *.db >nul 2>&1
	-@del /q "%TEMP%\*sysmanage*.db" >nul 2>&1
	-@del /q "%TEMP%\tmp*.db" >nul 2>&1
else
	@find . -name "*.db" -type f -delete 2>/dev/null || true
	@find /tmp -name "*sysmanage*.db" -type f -delete 2>/dev/null || true
	@find /tmp -name "tmp*.db" -type f -delete 2>/dev/null || true
endif
ifeq ($(OS),Windows_NT)
	@set OTEL_ENABLED=false && $(PYTHON) -m pytest tests/ --ignore=tests/ui/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=html
else
	@OTEL_ENABLED=false $(PYTHON) -m pytest tests/ --ignore=tests/ui/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=html
endif
	@echo "[OK] Python tests completed"

# TypeScript/React tests
test-typescript:
	@echo "=== Running TypeScript/React Tests ==="
	@cd frontend && npm run test:coverage
	@echo "[OK] TypeScript tests completed"

# UI integration tests
test-ui: $(VENV_ACTIVATE)
ifeq ($(OS),Windows_NT)
	@echo "=== Running UI Integration Tests (Playwright) ==="
	@echo "[INFO] Windows detected - testing Chrome and Firefox"
	@cmd /c "set OTEL_ENABLED=false && set PYTHONPATH=tests/ui;%PYTHONPATH% && $(PYTHON) -m pytest tests/ui/test_login_cross_browser.py --confcutdir=tests/ui -p tests.ui.conftest_playwright -v --tb=short"
	@echo "[OK] Playwright UI integration tests completed"
else
	@if [ "$(shell uname -s)" != "OpenBSD" ] && [ "$(shell uname -s)" != "FreeBSD" ] && [ "$(shell uname -s)" != "NetBSD" ]; then \
		echo "=== Running UI Integration Tests (Playwright) ==="; \
		if [ "$(shell uname -s)" = "Darwin" ]; then \
			echo "[INFO] macOS detected - testing Chrome, Firefox, and WebKit/Safari"; \
		else \
			echo "[INFO] Linux detected - testing Chrome and Firefox"; \
		fi; \
		OTEL_ENABLED=false PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_login_cross_browser.py --confcutdir=tests/ui -p tests.ui.conftest_playwright -v --tb=short; \
		echo "[OK] Playwright UI integration tests completed"; \
	else \
		echo "=== Running UI Integration Tests (Selenium) ==="; \
		echo "[INFO] Using Selenium fallback on BSD systems (OpenBSD/FreeBSD/NetBSD)"; \
		OTEL_ENABLED=false PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_login_selenium.py --confcutdir=tests/ui -p tests.ui.conftest_selenium -v --tb=short; \
		echo "[OK] Selenium UI integration tests completed"; \
	fi
endif

# Playwright tests only (alias for test-ui)
test-playwright: test-ui

# Performance testing with Artillery and enhanced Playwright
test-performance: $(VENV_ACTIVATE)
	@echo "=== Running Performance Tests ==="
ifeq ($(OS),Windows_NT)
	@echo "[INFO] Running Artillery load tests for backend API..."
	@where artillery >nul 2>nul || ( \
		echo "[ERROR] Artillery not found. Installing..." && \
		npm install -g artillery@latest \
	)
	@echo "[INFO] Running Artillery load tests against http://localhost:8001..."
	@echo "[NOTE] Ensure the SysManage server is running on port 8001"
	@artillery run artillery.yml --output artillery-report.json || echo "[WARNING] Artillery tests failed - continuing with Playwright performance tests"
	@if exist artillery-report.json ( \
		artillery report artillery-report.json --output artillery-report.html && \
		echo "[INFO] Artillery report generated: artillery-report.html" \
	)
	@echo "[INFO] Running Playwright performance tests..."
	@cmd /c "set OTEL_ENABLED=false && set PYTHONPATH=tests/ui;%PYTHONPATH% && $(PYTHON) -m pytest tests/ui/test_performance_playwright.py --confcutdir=tests/ui -p conftest_playwright -v --tb=short" || echo "[WARNING] Playwright performance tests failed"
	@echo "[INFO] Running performance regression analysis..."
	@$(PYTHON) scripts/performance_regression_check.py || echo "[WARNING] Performance regressions detected"
else
	@if [ "$(shell uname -s)" = "OpenBSD" ] || [ "$(shell uname -s)" = "FreeBSD" ] || [ "$(shell uname -s)" = "NetBSD" ]; then \
		echo "[SKIP] Artillery and Playwright not supported on $(shell uname -s) - performance tests skipped"; \
	else \
		echo "[INFO] Running Artillery load tests for backend API..."; \
		command -v artillery >/dev/null 2>&1 || { \
			echo "[ERROR] Artillery not found. Installing..."; \
			if command -v npm >/dev/null 2>&1; then \
				npm install -g artillery@latest; \
			else \
				echo "[ERROR] npm not found. Please install Node.js and npm first."; \
				exit 1; \
			fi; \
		}; \
		echo "[INFO] Running Artillery load tests against http://localhost:8001..."; \
		echo "[NOTE] Ensure the SysManage server is running on port 8001"; \
		artillery run artillery.yml --output artillery-report.json || { \
			echo "[WARNING] Artillery tests failed - continuing with Playwright performance tests"; \
		}; \
		if [ -f artillery-report.json ]; then \
			artillery report artillery-report.json --output artillery-report.html; \
			echo "[INFO] Artillery report generated: artillery-report.html"; \
		fi; \
		echo "[INFO] Running Playwright performance tests..."; \
		OTEL_ENABLED=false PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_performance_playwright.py --confcutdir=tests/ui -p conftest_playwright -v --tb=short || echo "[WARNING] Playwright performance tests failed"; \
		echo "[INFO] Running performance regression analysis..."; \
		$(PYTHON) scripts/performance_regression_check.py || echo "[WARNING] Performance regressions detected"; \
	fi
endif
	@echo "[OK] Performance testing completed"

# Vite tests only (alias for test-typescript)
test-vite: test-typescript

# Model synchronization check
check-test-models:
	@echo "=== Checking Test Model Synchronization ==="
	@$(PYTHON) scripts/check_test_models.py

# Combined testing
test: test-python test-typescript test-ui test-performance
	@echo "[OK] All tests completed successfully!"

# Build frontend for production
build:
	@echo "=== Building Frontend ==="
	@echo "Building React frontend with Vite..."
	@cd frontend && npm run build
	@echo "[OK] Frontend build completed - output in frontend/dist/"

# Clean artifacts
clean:
	@echo "Cleaning test artifacts and cache..."
ifeq ($(OS),Windows_NT)
	-@del /s /q *.pyc >nul 2>&1
	-@rmdir /s /q __pycache__ >nul 2>&1
	-@rmdir /s /q .pytest_cache >nul 2>&1
	-@rmdir /s /q htmlcov >nul 2>&1
	-@del /q .coverage >nul 2>&1
	-@rmdir /s /q frontend\coverage >nul 2>&1
	-@rmdir /s /q frontend\dist >nul 2>&1
else
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov/ .coverage
	@cd frontend && rm -rf coverage/ dist/ 2>/dev/null || true
endif
	@echo "[OK] Clean completed"

# Server management targets with shell detection
start:
	@echo "Stopping any existing processes..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/stop.ps1 2>nul || echo "No processes to stop"
else
	@./scripts/stop.sh 2>/dev/null || echo "No processes to stop"
endif
	@echo ""
	@echo "Starting OpenBAO development server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/start-openbao-nohup.ps1
else
	@./scripts/start-openbao.sh
endif
	@echo ""
	@echo "Starting telemetry services..."
	@$(MAKE) start-telemetry
	@echo ""
	@echo "Starting SysManage server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/start-nohup.ps1
else
	@if [ -n "$$ZSH_VERSION" ]; then \
		echo "Detected zsh shell, using start.sh"; \
		./scripts/start.sh; \
	elif [ -n "$$BASH_VERSION" ]; then \
		echo "Detected bash shell, using start.sh"; \
		./scripts/start.sh; \
	elif [ -n "$$KSH_VERSION" ]; then \
		echo "Detected ksh shell, using start.sh"; \
		./scripts/start.sh; \
	else \
		echo "Detected POSIX shell, using start.sh"; \
		./scripts/start.sh; \
	fi
endif

stop:
	@echo "Stopping SysManage server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/stop.ps1 || scripts\stop.cmd
else
	@if [ -n "$$ZSH_VERSION" ]; then \
		echo "Detected zsh shell, using stop.sh"; \
		./scripts/stop.sh; \
	elif [ -n "$$BASH_VERSION" ]; then \
		echo "Detected bash shell, using stop.sh"; \
		./scripts/stop.sh; \
	elif [ -n "$$KSH_VERSION" ]; then \
		echo "Detected ksh shell, using stop.sh"; \
		./scripts/stop.sh; \
	else \
		echo "Detected POSIX shell, using stop.sh"; \
		./scripts/stop.sh; \
	fi
endif
	@echo ""
	@echo "Stopping telemetry services..."
	@$(MAKE) stop-telemetry
	@echo ""
	@echo "Stopping OpenBAO development server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/stop-openbao.ps1 || scripts\stop-openbao.cmd
else
	@./scripts/stop-openbao.sh
endif

# OpenBAO (Vault) management targets
start-openbao:
	@echo "Starting OpenBAO development server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/start-openbao.ps1 || scripts\start-openbao.cmd
else
	@./scripts/start-openbao.sh
endif

stop-openbao:
	@echo "Stopping OpenBAO development server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/stop-openbao.ps1 || scripts\stop-openbao.cmd
else
	@./scripts/stop-openbao.sh
endif

status-openbao:
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/status-openbao.ps1 || scripts\status-openbao.cmd
else
	@./scripts/status-openbao.sh
endif

# Development server targets (legacy compatibility)
run-dev: start
	@echo "Legacy run-dev target - use 'make start' instead"

stop-dev: stop
	@echo "Legacy stop-dev target - use 'make stop' instead"

# Telemetry management targets (installation happens in install-dev)
start-telemetry:
	@echo "Starting telemetry services..."
ifeq ($(OS),Windows_NT)
	@echo "Starting OpenTelemetry Collector..."
	-@powershell -Command "if (Test-Path '$(USERPROFILE)\AppData\Local\bin\otelcol-contrib.exe') { Start-Process -FilePath '$(USERPROFILE)\AppData\Local\bin\otelcol-contrib.exe' -ArgumentList '--config=config/otel-collector-config.yml' -WindowStyle Minimized -PassThru | ForEach-Object { $$_.Id | Out-File -FilePath 'logs/otel-collector.pid' -Encoding ASCII } } else { Write-Host '[WARNING] otelcol-contrib.exe not found. Run make install-dev first.' }; exit 0"
	@echo "Starting Prometheus..."
	-@powershell -Command "if (-not (Test-Path 'data/prometheus')) { New-Item -ItemType Directory -Path 'data/prometheus' -Force | Out-Null }; Remove-Item 'data/prometheus/queries.active' -ErrorAction SilentlyContinue; exit 0"
	-@powershell -Command "if (Test-Path '$(USERPROFILE)\AppData\Local\bin\prometheus.exe') { Start-Process -FilePath '$(USERPROFILE)\AppData\Local\bin\prometheus.exe' -ArgumentList '--config.file=config/prometheus.yml','--web.listen-address=:9091','--storage.tsdb.path=data/prometheus' -WindowStyle Minimized -PassThru | ForEach-Object { $$_.Id | Out-File -FilePath 'logs/prometheus.pid' -Encoding ASCII } } else { Write-Host '[WARNING] prometheus.exe not found. Run make install-dev first.' }; exit 0"
else
	@echo "Starting OpenTelemetry Collector..."
	@if command -v otelcol-contrib >/dev/null 2>&1; then \
		OTEL_CONFIG="config/otel-collector-config.yml"; \
		if [ "$$(uname -s)" = "OpenBSD" ] && [ -f "config/otel-collector-config-openbsd.yml" ]; then \
			OTEL_CONFIG="config/otel-collector-config-openbsd.yml"; \
			echo "Using OpenBSD-specific OTel config"; \
		elif [ "$$(uname -s)" = "NetBSD" ] && [ -f "config/otel-collector-config-netbsd.yml" ]; then \
			OTEL_CONFIG="config/otel-collector-config-netbsd.yml"; \
			echo "Using NetBSD-specific OTel config"; \
		fi; \
		nohup otelcol-contrib --config=$$OTEL_CONFIG > logs/otel-collector.log 2>&1 & echo $$! > logs/otel-collector.pid; \
		echo "OpenTelemetry Collector started (PID: $$(cat logs/otel-collector.pid))"; \
	else \
		echo "[WARNING] otelcol-contrib not found. Run 'make install-dev' first."; \
	fi
	@echo "Starting Prometheus..."
	@PROMETHEUS_BIN=""; \
	if [ -f "$$HOME/.local/bin/prometheus" ]; then \
		PROMETHEUS_BIN="$$HOME/.local/bin/prometheus"; \
	elif command -v prometheus >/dev/null 2>&1; then \
		PROMETHEUS_BIN="prometheus"; \
	fi; \
	if [ -n "$$PROMETHEUS_BIN" ]; then \
		if [ ! -d "data/prometheus" ]; then \
			if [ "$$(uname -s)" = "OpenBSD" ]; then \
				doas mkdir -p data/prometheus && doas chown -R $(USER):$(USER) data/prometheus; \
			else \
				mkdir -p data/prometheus; \
			fi; \
		fi; \
		nohup $$PROMETHEUS_BIN --config.file=config/prometheus.yml --web.listen-address=:9091 --storage.tsdb.path=./data/prometheus --storage.tsdb.retention.time=15d --storage.tsdb.retention.size=10GB > logs/prometheus.log 2>&1 & echo $$! > logs/prometheus.pid; \
		echo "Prometheus started (PID: $$(cat logs/prometheus.pid))"; \
	else \
		echo "[WARNING] prometheus not found. Run 'make install-dev' first."; \
	fi
endif
	@echo ""
	@echo "[OK] Telemetry services started successfully"
	@echo "  - OpenTelemetry Collector: http://localhost:4317 (gRPC), http://localhost:4318 (HTTP)"
	@echo "  - OpenTelemetry Collector UI: http://localhost:55679"
	@echo "  - Prometheus: http://localhost:9091"
	@echo "  - Prometheus metrics scraper: http://localhost:9090 (from SysManage backend)"
	@echo ""
	@echo "Note: OpenTelemetry is enabled by default. To disable, set OTEL_ENABLED=false"

stop-telemetry:
	@echo "Stopping telemetry services..."
ifeq ($(OS),Windows_NT)
	@powershell -Command "Get-Process otelcol-contrib -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" 2>nul || exit 0
	@if exist logs\otel-collector.pid del logs\otel-collector.pid 2>nul
	@powershell -Command "Get-Process prometheus -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" 2>nul || exit 0
	@if exist logs\prometheus.pid del logs\prometheus.pid 2>nul
else
	@if [ -f logs/otel-collector.pid ]; then \
		kill $$(cat logs/otel-collector.pid) 2>/dev/null || true; \
		rm -f logs/otel-collector.pid; \
		echo "OpenTelemetry Collector stopped"; \
	fi
	@if [ -f logs/prometheus.pid ]; then \
		kill $$(cat logs/prometheus.pid) 2>/dev/null || true; \
		rm -f logs/prometheus.pid; \
		echo "Prometheus stopped"; \
	fi
endif
	@echo "[OK] Telemetry services stopped"

status-telemetry:
	@echo "=== Telemetry Services Status ==="
ifeq ($(OS),Windows_NT)
	@if exist logs\otel-collector.pid (powershell -Command "Get-Process -Id (Get-Content logs\otel-collector.pid) -ErrorAction SilentlyContinue" && echo "OpenTelemetry Collector: RUNNING") else (echo "OpenTelemetry Collector: STOPPED")
	@if exist logs\prometheus.pid (powershell -Command "Get-Process -Id (Get-Content logs\prometheus.pid) -ErrorAction SilentlyContinue" && echo "Prometheus: RUNNING") else (echo "Prometheus: STOPPED")
else
	@if [ -f logs/otel-collector.pid ]; then \
		if ps -p $$(cat logs/otel-collector.pid) > /dev/null 2>&1; then \
			echo "OpenTelemetry Collector: RUNNING (PID: $$(cat logs/otel-collector.pid))"; \
		else \
			echo "OpenTelemetry Collector: STOPPED (stale PID file)"; \
			rm -f logs/otel-collector.pid; \
		fi; \
	else \
		echo "OpenTelemetry Collector: STOPPED"; \
	fi
	@if [ -f logs/prometheus.pid ]; then \
		if ps -p $$(cat logs/prometheus.pid) > /dev/null 2>&1; then \
			echo "Prometheus: RUNNING (PID: $$(cat logs/prometheus.pid))"; \
		else \
			echo "Prometheus: STOPPED (stale PID file)"; \
			rm -f logs/prometheus.pid; \
		fi; \
	else \
		echo "Prometheus: STOPPED"; \
	fi
endif
	@echo ""
	@echo "Service URLs:"
	@echo "  - OpenTelemetry Collector gRPC: http://localhost:4317"
	@echo "  - OpenTelemetry Collector HTTP: http://localhost:4318"
	@echo "  - OpenTelemetry Collector UI: http://localhost:55679"
	@echo "  - Prometheus: http://localhost:9091"

# OpenBSD grpcio build target
build-grpcio-openbsd: $(VENV_ACTIVATE)
	@echo "=== Building grpcio for OpenBSD ==="
	@echo "[INFO] Uninstalling any existing grpcio..."
	@$(PYTHON) -m pip uninstall -y grpcio 2>/dev/null || true
	@mkdir -p $$HOME/tmp
	@export TMPDIR=$$HOME/tmp && \
	PYTHON_PATH=$$(cd $(CURDIR) && pwd)/$(PYTHON) && \
	echo "[INFO] Downloading grpcio source for patching..." && \
	$$PYTHON_PATH -m pip download --no-binary=grpcio --no-deps grpcio==1.71.0 -d $$HOME/tmp/ && \
	cd $$HOME/tmp && tar -xzf grpcio-1.71.0.tar.gz && \
	echo "[INFO] Applying OpenBSD patches from ports..." && \
	cd $$HOME/tmp/grpcio-1.71.0 && \
	PATCH_DIR=$$(cd $(CURDIR) && pwd)/patches/openbsd-grpc && \
	ABSEIL_PATCH=$$(cd $(CURDIR) && pwd)/patches/abseil-commonfields.patch && \
	ARES_PATCH=$$(cd $(CURDIR) && pwd)/patches/grpcio-ares-openbsd.patch && \
	patch -p0 < $$PATCH_DIR/patch-src_core_util_posix_directory_reader_cc && \
	patch -p1 < $$ABSEIL_PATCH && \
	patch -p1 < $$ARES_PATCH && \
	echo "[INFO] Configuring build to use bundled abseil (not system abseil)..." && \
	export CFLAGS="-isystem /usr/local/include" && \
	export CXXFLAGS="-std=c++17 -fpermissive -Wno-error -isystem /usr/local/include" && \
	export LDFLAGS="-L/usr/local/lib -Wl,-R/usr/local/lib" && \
	export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
	export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
	export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
	export GRPC_PYTHON_BUILD_WITH_BORING_SSL_ASM="" && \
	export GRPC_PYTHON_DISABLE_LIBC_COMPATIBILITY=1 && \
	export GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS=1 && \
	echo "[INFO] Building patched grpcio from source (this may take 5-10 minutes)..." && \
	$$PYTHON_PATH -m pip install --no-cache-dir --no-binary=:all: -v . 2>&1 | tee $$HOME/tmp/grpcio-build.log; \
	BUILD_RESULT=$$?; \
	if [ $$BUILD_RESULT -ne 0 ]; then \
		echo "[ERROR] grpcio build failed with exit code $$BUILD_RESULT"; \
		echo "[ERROR] Check log at $$HOME/tmp/grpcio-build.log"; \
		cd $(CURDIR) && rm -rf $$HOME/tmp/grpcio-1.71.0; \
		exit 1; \
	fi && \
	rm -rf $$HOME/tmp/grpcio-1.71.0* && \
	echo "[OK] grpcio 1.71.0 build completed successfully with OpenBSD patches"
# Installer targets
installer: build
	@echo "=== Auto-detecting platform for installer build ==="
	@if [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "OpenBSD detected - building port tarball"; \
		$(MAKE) installer-openbsd; \
	elif [ "$$(uname -s)" = "FreeBSD" ]; then \
		echo "FreeBSD detected - .pkg not yet implemented"; \
		exit 1; \
	elif [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "NetBSD detected - building .tgz package"; \
		$(MAKE) installer-netbsd; \
	elif [ -f /etc/os-release ]; then \
		. /etc/os-release; \
		if [ "$$ID" = "opensuse-leap" ] || [ "$$ID" = "opensuse-tumbleweed" ] || [ "$$ID" = "sles" ]; then \
			echo "openSUSE/SLES system detected - building RPM package"; \
			$(MAKE) installer-rpm-opensuse; \
		elif [ -f /etc/redhat-release ]; then \
			echo "Red Hat-based system detected - building RPM package"; \
			$(MAKE) installer-rpm-centos; \
		elif [ -f /etc/debian_version ] || [ -f /etc/lsb-release ]; then \
			echo "Debian-based system detected - building DEB package"; \
			$(MAKE) installer-deb; \
		else \
			echo "Unknown Linux distribution - cannot auto-detect installer type"; \
			exit 1; \
		fi; \
	else \
		echo "Unknown platform - cannot auto-detect installer type"; \
		exit 1; \
	fi

installer-deb:
	@echo "=== Building Ubuntu/Debian .deb Package ==="
	@echo ""
	@echo "Checking build dependencies..."
	@command -v dpkg-buildpackage >/dev/null 2>&1 || { \
		echo "ERROR: dpkg-buildpackage not found."; \
		echo "Install with: make install-dev"; \
		echo "Or manually: sudo apt-get install -y debhelper dh-python python3-all build-essential devscripts lintian nodejs npm"; \
		exit 1; \
	}
	@echo "✓ Build tools available"
	@echo ""
	@echo "Determining version..."
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Building version: $$VERSION"; \
		fi; \
	fi; \
	echo ""; \
	echo "Building frontend..."; \
	cd frontend && npm run build && cd ..; \
	echo "✓ Frontend build complete"; \
	echo ""; \
	echo "Generating Software Bill of Materials (SBOM)..."; \
	$(MAKE) sbom; \
	echo ""; \
	echo "Creating build directory..."; \
	CURRENT_DIR=$$(pwd); \
	BUILD_TEMP="$$CURRENT_DIR/installer/dist/build-temp"; \
	BUILD_DIR="$$BUILD_TEMP/sysmanage-$$VERSION"; \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	mkdir -p "$$OUTPUT_DIR"; \
	rm -rf "$$BUILD_TEMP"; \
	mkdir -p "$$BUILD_DIR"; \
	echo "✓ Build directory created: $$BUILD_DIR"; \
	echo ""; \
	echo "Copying source files..."; \
	rsync -a --exclude='htmlcov' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='node_modules' --exclude='.venv' backend/ "$$BUILD_DIR/backend/"; \
	mkdir -p "$$BUILD_DIR/frontend"; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/dist/ "$$BUILD_DIR/frontend/dist/"; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/public/ "$$BUILD_DIR/frontend/public/"; \
	cp requirements.txt "$$BUILD_DIR/"; \
	cp alembic.ini "$$BUILD_DIR/"; \
	cp -r config "$$BUILD_DIR/" 2>/dev/null || true; \
	cp -r scripts "$$BUILD_DIR/" 2>/dev/null || true; \
	cp README.md "$$BUILD_DIR/" 2>/dev/null || touch "$$BUILD_DIR/README.md"; \
	mkdir -p "$$BUILD_DIR/sbom"; \
	cp sbom/*.json "$$BUILD_DIR/sbom/" 2>/dev/null || echo "Note: SBOM files not found, skipping"; \
	echo "✓ Application source copied"; \
	echo ""; \
	echo "Copying Debian packaging files..."; \
	cp -r installer/ubuntu/debian "$$BUILD_DIR/"; \
	mkdir -p "$$BUILD_DIR/installer/ubuntu"; \
	cp installer/ubuntu/*.service "$$BUILD_DIR/installer/ubuntu/"; \
	cp installer/ubuntu/*.example "$$BUILD_DIR/installer/ubuntu/"; \
	cp installer/ubuntu/*.conf "$$BUILD_DIR/installer/ubuntu/" 2>/dev/null || true; \
	echo "✓ Packaging files copied"; \
	echo ""; \
	echo "Building package..."; \
	cd "$$BUILD_DIR" && dpkg-buildpackage -d -us -uc -b; \
	echo ""; \
	echo "Moving package to output directory..."; \
	mv "$$BUILD_TEMP"/sysmanage_*.deb "$$OUTPUT_DIR/"; \
	mv "$$BUILD_TEMP"/sysmanage_*.buildinfo "$$OUTPUT_DIR/" 2>/dev/null || true; \
	mv "$$BUILD_TEMP"/sysmanage_*.changes "$$OUTPUT_DIR/" 2>/dev/null || true; \
	echo ""; \
	echo "Cleaning up build directory..."; \
	rm -rf "$$BUILD_TEMP"; \
	echo ""; \
	echo "✓ Package built successfully!"; \
	echo ""; \
	echo "Package location: $$OUTPUT_DIR/sysmanage_$$VERSION-1_all.deb"; \
	echo ""; \
	echo "To install:"; \
	echo "  sudo dpkg -i $$OUTPUT_DIR/sysmanage_$$VERSION-1_all.deb"; \
	echo "  sudo apt-get install -f  # If dependencies are missing"; \
	echo ""; \
	echo "After installation:"; \
	echo "  1. Configure /etc/sysmanage.yaml (use https://sysmanage.org/config-builder.html)"; \
	echo "  2. Set up PostgreSQL database"; \
	echo "  3. Run: cd /opt/sysmanage && sudo -u sysmanage .venv/bin/python -m alembic upgrade head"; \
	echo "  4. Start: sudo systemctl start sysmanage"

# Build OpenBSD port tarball
installer-openbsd:
	@echo "=== Building OpenBSD Port Tarball ==="
	@echo ""
	@CURRENT_DIR=$$(pwd); \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	PORT_DIR="$$CURRENT_DIR/installer/openbsd"; \
	echo "Determining version from git..."; \
	VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
	if [ -z "$$VERSION" ]; then \
		VERSION="0.1.0"; \
		echo "WARNING: No git tags found, using default version: $$VERSION"; \
	else \
		echo "Building version: $$VERSION"; \
	fi; \
	echo ""; \
	echo "Checking prerequisites..."; \
	if [ ! -d frontend/dist ]; then \
		echo "ERROR: Frontend not built. Run 'make build' first."; \
		exit 1; \
	fi; \
	echo "✓ Frontend build found"; \
	echo ""; \
	echo "Updating port Makefile with version v$$VERSION..."; \
	sed -i.bak "s/^GH_TAGNAME =.*/GH_TAGNAME =\t\tv$$VERSION/" "$$PORT_DIR/Makefile"; \
	rm -f "$$PORT_DIR/Makefile.bak"; \
	echo "✓ Version updated"; \
	echo ""; \
	echo "Creating output directory..."; \
	mkdir -p "$$OUTPUT_DIR"; \
	echo "✓ Output directory ready: $$OUTPUT_DIR"; \
	echo ""; \
	echo "Creating port tarball..."; \
	cd installer && tar czf "$$OUTPUT_DIR/sysmanage-openbsd-port-$$VERSION.tar.gz" openbsd/; \
	cd "$$CURRENT_DIR"; \
	echo ""; \
	echo "✓ OpenBSD port tarball created: $$OUTPUT_DIR/sysmanage-openbsd-port-$$VERSION.tar.gz"; \
	echo ""; \
	ls -lh "$$OUTPUT_DIR/sysmanage-openbsd-port-$$VERSION.tar.gz"; \
	echo ""; \
	echo "==================================="; \
	echo "OpenBSD Port Build Complete!"; \
	echo "==================================="; \
	echo ""; \
	echo "To use this port:"; \
	echo "  1. Extract to OpenBSD ports tree:"; \
	echo "     cd /usr/ports/mystuff && mkdir -p www"; \
	echo "     tar xzf $$OUTPUT_DIR/sysmanage-openbsd-port-$$VERSION.tar.gz -C www/"; \
	echo ""; \
	echo "  2. Generate checksums:"; \
	echo "     cd /usr/ports/mystuff/www/openbsd"; \
	echo "     doas make makesum"; \
	echo ""; \
	echo "  3. Build and install:"; \
	echo "     doas make install"; \
	echo ""; \
	echo "See installer/openbsd/README.md for full instructions"

# Build CentOS/RHEL/Fedora RPM package
installer-rpm-centos:
	@echo "=== Building CentOS/RHEL/Fedora .rpm Package ==="
	@echo ""
	@echo "Checking build dependencies..."
	@command -v rpmbuild >/dev/null 2>&1 || { \
		echo "ERROR: rpmbuild not found."; \
		echo "Install with: sudo dnf install -y rpm-build rpmdevtools python3-devel python3-setuptools"; \
		echo "Or run: make install-dev"; \
		exit 1; \
	}
	@echo "✓ Build tools available"
	@echo ""
	@set -e; \
	echo "Determining version..."; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Building version: $$VERSION"; \
		fi; \
	fi; \
	echo ""; \
	echo "Building frontend..."; \
	cd frontend && npm run build && cd ..; \
	echo "✓ Frontend build complete"; \
	echo ""; \
	echo "Generating SBOM files..."; \
	$(MAKE) sbom; \
	echo "✓ SBOM files generated"; \
	echo ""; \
	echo "Setting up RPM build tree..."; \
	CURRENT_DIR=$$(pwd); \
	BUILD_TEMP="$$CURRENT_DIR/installer/dist/rpmbuild"; \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	mkdir -p "$$OUTPUT_DIR"; \
	rm -rf "$$BUILD_TEMP"; \
	mkdir -p "$$BUILD_TEMP"/BUILD "$$BUILD_TEMP"/RPMS "$$BUILD_TEMP"/SOURCES "$$BUILD_TEMP"/SPECS "$$BUILD_TEMP"/SRPMS; \
	echo "✓ RPM build tree created"; \
	echo ""; \
	echo "Creating source tarball..."; \
	TAR_NAME="sysmanage-$$VERSION"; \
	TAR_DIR="$$BUILD_TEMP/SOURCES/$$TAR_NAME"; \
	mkdir -p "$$TAR_DIR"; \
	rsync -a --exclude='node_modules' --exclude='htmlcov' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.venv' --exclude='installer/dist' backend/ "$$TAR_DIR/backend/"; \
	mkdir -p "$$TAR_DIR/frontend"; \
	rsync -a --exclude='node_modules' --exclude='src' frontend/dist/ "$$TAR_DIR/frontend/dist/"; \
	rsync -a --exclude='node_modules' --exclude='src' frontend/public/ "$$TAR_DIR/frontend/public/"; \
	cp alembic.ini "$$TAR_DIR/"; \
	cp requirements.txt "$$TAR_DIR/"; \
	cp -r alembic "$$TAR_DIR/"; \
	cp -r config "$$TAR_DIR/"; \
	cp -r scripts "$$TAR_DIR/"; \
	cp -r sbom "$$TAR_DIR/"; \
	cp README.md "$$TAR_DIR/" 2>/dev/null || touch "$$TAR_DIR/README.md"; \
	cp LICENSE "$$TAR_DIR/" 2>/dev/null || touch "$$TAR_DIR/LICENSE"; \
	mkdir -p "$$TAR_DIR/installer/centos"; \
	cp installer/centos/*.service "$$TAR_DIR/installer/centos/"; \
	cp installer/centos/*.conf "$$TAR_DIR/installer/centos/"; \
	cp installer/centos/*.example "$$TAR_DIR/installer/centos/"; \
	cd "$$BUILD_TEMP/SOURCES" && tar czf "sysmanage-$$VERSION.tar.gz" "$$TAR_NAME/"; \
	rm -rf "$$TAR_DIR"; \
	echo "✓ Source tarball created"; \
	echo ""; \
	echo "Updating spec file with version..."; \
	cp "$$CURRENT_DIR/installer/centos/sysmanage.spec" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	DATE=$$(date "+%a %b %d %Y"); \
	sed -i "s/^Version:.*/Version:        $$VERSION/" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	sed -i "s/^\\* Tue Oct 29 2025/\\* $$DATE/" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	echo "✓ Spec file updated to version $$VERSION"; \
	echo ""; \
	echo "Building RPM package..."; \
	cd "$$BUILD_TEMP" && rpmbuild --define "_topdir $$BUILD_TEMP" --nodeps -bb SPECS/sysmanage.spec 2>&1 | tee build.log; \
	BUILD_STATUS=$$?; \
	if [ $$BUILD_STATUS -eq 0 ]; then \
		echo ""; \
		echo "✓ Package built successfully!"; \
		echo ""; \
		echo "Moving package to output directory..."; \
		RPM_FILE=$$(find "$$BUILD_TEMP/RPMS" -name "sysmanage-$$VERSION-*.rpm" | head -1); \
		if [ -n "$$RPM_FILE" ]; then \
			cp "$$RPM_FILE" "$$OUTPUT_DIR/"; \
			RPM_BASENAME=$$(basename "$$RPM_FILE"); \
			echo "✓ Package moved to: $$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			cd "$$OUTPUT_DIR" && sha256sum "$$RPM_BASENAME" > "$$RPM_BASENAME.sha256"; \
			echo "✓ SHA256 checksum: $$OUTPUT_DIR/$$RPM_BASENAME.sha256"; \
			echo ""; \
			echo "==================================="; \
			echo "CentOS/RHEL RPM Build Complete!"; \
			echo "==================================="; \
			echo ""; \
			ls -lh "$$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			rpm -qip "$$OUTPUT_DIR/$$RPM_BASENAME" | head -20; \
			echo ""; \
			echo "To install:"; \
			echo "  sudo dnf install $$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			echo "After installation:"; \
			echo "  1. Configure /etc/sysmanage.yaml"; \
			echo "  2. Set up PostgreSQL database"; \
			echo "  3. Run: cd /opt/sysmanage && sudo -u sysmanage .venv/bin/python -m alembic upgrade head"; \
			echo "  4. Start: sudo systemctl start sysmanage"; \
		else \
			echo "ERROR: Could not find built RPM package"; \
			exit 1; \
		fi; \
	else \
		echo ""; \
		echo "ERROR: RPM build failed!"; \
		echo "Check the build log: $$BUILD_TEMP/build.log"; \
		tail -50 "$$BUILD_TEMP/build.log"; \
		exit 1; \
	fi

# Build OpenSUSE/SLES RPM package with vendor dependencies
installer-rpm-opensuse:
	@echo "=== Building OpenSUSE/SLES .rpm Package ==="
	@echo ""
	@echo "Checking build dependencies..."
	@command -v rpmbuild >/dev/null 2>&1 || { \
		echo "ERROR: rpmbuild not found."; \
		echo "Install with: sudo zypper install rpm-build python311-devel python311-pip"; \
		echo "Or run: make install-dev"; \
		exit 1; \
	}
	@echo "✓ Build tools available"
	@echo ""
	@set -e; \
	echo "Determining version..."; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Building version: $$VERSION"; \
		fi; \
	fi; \
	echo ""; \
	echo "Building frontend..."; \
	cd frontend && npm run build && cd ..; \
	echo "✓ Frontend build complete"; \
	echo ""; \
	echo "Generating SBOM files..."; \
	$(MAKE) sbom; \
	echo "✓ SBOM files generated"; \
	echo ""; \
	echo "Downloading Python vendor dependencies for offline installation..."; \
	VENDOR_DIR="$$(pwd)/vendor"; \
	rm -rf "$$VENDOR_DIR"; \
	mkdir -p "$$VENDOR_DIR"; \
	pip3 download -r requirements.txt -d "$$VENDOR_DIR" --no-binary :all: 2>/dev/null || \
	pip3 download -r requirements.txt -d "$$VENDOR_DIR"; \
	echo "✓ Vendor dependencies downloaded"; \
	echo ""; \
	echo "Setting up RPM build tree..."; \
	CURRENT_DIR=$$(pwd); \
	BUILD_TEMP="$$CURRENT_DIR/installer/dist/rpmbuild-opensuse"; \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	mkdir -p "$$OUTPUT_DIR"; \
	rm -rf "$$BUILD_TEMP"; \
	mkdir -p "$$BUILD_TEMP"/BUILD "$$BUILD_TEMP"/RPMS "$$BUILD_TEMP"/SOURCES "$$BUILD_TEMP"/SPECS "$$BUILD_TEMP"/SRPMS; \
	echo "✓ RPM build tree created"; \
	echo ""; \
	echo "Creating source tarball..."; \
	TAR_NAME="sysmanage-$$VERSION"; \
	TAR_DIR="$$BUILD_TEMP/SOURCES/$$TAR_NAME"; \
	mkdir -p "$$TAR_DIR"; \
	rsync -a --exclude='node_modules' --exclude='htmlcov' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.venv' --exclude='installer/dist' backend/ "$$TAR_DIR/backend/"; \
	mkdir -p "$$TAR_DIR/frontend"; \
	rsync -a --exclude='node_modules' --exclude='src' frontend/dist/ "$$TAR_DIR/frontend/dist/"; \
	rsync -a --exclude='node_modules' --exclude='src' frontend/public/ "$$TAR_DIR/frontend/public/"; \
	cp alembic.ini "$$TAR_DIR/"; \
	cp requirements.txt "$$TAR_DIR/"; \
	cp -r alembic "$$TAR_DIR/"; \
	cp -r config "$$TAR_DIR/"; \
	cp -r scripts "$$TAR_DIR/"; \
	cp -r sbom "$$TAR_DIR/"; \
	cp README.md "$$TAR_DIR/" 2>/dev/null || touch "$$TAR_DIR/README.md"; \
	cp LICENSE "$$TAR_DIR/" 2>/dev/null || touch "$$TAR_DIR/LICENSE"; \
	mkdir -p "$$TAR_DIR/installer/opensuse"; \
	cp installer/opensuse/*.service "$$TAR_DIR/installer/opensuse/"; \
	cp installer/opensuse/*.conf "$$TAR_DIR/installer/opensuse/"; \
	cp installer/opensuse/*.example "$$TAR_DIR/installer/opensuse/"; \
	cd "$$BUILD_TEMP/SOURCES" && tar czf "sysmanage-$$VERSION.tar.gz" "$$TAR_NAME/"; \
	rm -rf "$$TAR_DIR"; \
	echo "✓ Source tarball created"; \
	echo ""; \
	echo "Creating vendor tarball..."; \
	cd "$$CURRENT_DIR" && tar czf "$$BUILD_TEMP/SOURCES/sysmanage-vendor-$$VERSION.tar.gz" vendor/; \
	echo "✓ Vendor tarball created"; \
	echo ""; \
	echo "Updating spec file with version..."; \
	cp "$$CURRENT_DIR/installer/opensuse/sysmanage.spec" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	DATE=$$(date "+%a %b %d %Y"); \
	sed -i "s/^Version:.*/Version:        $$VERSION/" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	sed -i "s/^\\* Tue Oct 29 2025/\\* $$DATE/" "$$BUILD_TEMP/SPECS/sysmanage.spec"; \
	echo "✓ Spec file updated to version $$VERSION"; \
	echo ""; \
	echo "Building RPM package..."; \
	cd "$$BUILD_TEMP" && rpmbuild --define "_topdir $$BUILD_TEMP" --nodeps -bb SPECS/sysmanage.spec 2>&1 | tee build.log; \
	BUILD_STATUS=$$?; \
	if [ $$BUILD_STATUS -eq 0 ]; then \
		echo ""; \
		echo "✓ Package built successfully!"; \
		echo ""; \
		echo "Moving package to output directory..."; \
		RPM_FILE=$$(find "$$BUILD_TEMP/RPMS" -name "sysmanage-$$VERSION-*.rpm" | head -1); \
		if [ -n "$$RPM_FILE" ]; then \
			cp "$$RPM_FILE" "$$OUTPUT_DIR/"; \
			RPM_BASENAME=$$(basename "$$RPM_FILE"); \
			echo "✓ Package moved to: $$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			cd "$$OUTPUT_DIR" && sha256sum "$$RPM_BASENAME" > "$$RPM_BASENAME.sha256"; \
			echo "✓ SHA256 checksum: $$OUTPUT_DIR/$$RPM_BASENAME.sha256"; \
			echo ""; \
			echo "==================================="; \
			echo "OpenSUSE/SLES RPM Build Complete!"; \
			echo "==================================="; \
			echo ""; \
			ls -lh "$$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			rpm -qip "$$OUTPUT_DIR/$$RPM_BASENAME" | head -20; \
			echo ""; \
			echo "To install:"; \
			echo "  sudo zypper install $$OUTPUT_DIR/$$RPM_BASENAME"; \
			echo ""; \
			echo "After installation:"; \
			echo "  1. Configure /etc/sysmanage.yaml"; \
			echo "  2. Set up PostgreSQL database"; \
			echo "  3. Run: cd /opt/sysmanage && sudo -u sysmanage .venv/bin/python -m alembic upgrade head"; \
			echo "  4. Start: sudo systemctl start sysmanage"; \
		else \
			echo "ERROR: Could not find built RPM package"; \
			exit 1; \
		fi; \
	else \
		echo ""; \
		echo "ERROR: RPM build failed!"; \
		echo "Check the build log: $$BUILD_TEMP/build.log"; \
		tail -50 "$$BUILD_TEMP/build.log"; \
		exit 1; \
	fi; \
	rm -rf "$$VENDOR_DIR"

# NetBSD .tgz package
installer-netbsd:
	@echo "=== Building NetBSD Package ==="
	@echo ""
	@echo "Creating NetBSD .tgz package for sysmanage..."
	@echo ""
	@CURRENT_DIR=$$(pwd); \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	BUILD_DIR="$$CURRENT_DIR/build/netbsd"; \
	PACKAGE_ROOT="$$BUILD_DIR/package-root"; \
	echo "Determining version from git..."; \
	VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
	if [ -z "$$VERSION" ]; then \
		VERSION="0.1.0"; \
		echo "WARNING: No git tags found, using default version: $$VERSION"; \
	else \
		echo "Building version: $$VERSION"; \
	fi; \
	echo ""; \
	echo "Checking prerequisites..."; \
	if [ ! -d frontend/dist ]; then \
		echo "ERROR: Frontend not built. Run 'make build' first."; \
		exit 1; \
	fi; \
	echo "✓ Frontend build found"; \
	echo ""; \
	echo "Generating SBOM files..."; \
	$(MAKE) sbom; \
	echo "✓ SBOM files generated"; \
	echo ""; \
	echo "Cleaning build directory..."; \
	rm -rf "$$BUILD_DIR"; \
	mkdir -p "$$PACKAGE_ROOT"; \
	echo "✓ Build directory prepared: $$BUILD_DIR"; \
	echo ""; \
	echo "Creating package directory structure..."; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/etc/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/examples/rc.d"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/examples/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/var/lib/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/var/log/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/var/run/sysmanage"; \
	echo "✓ Package directories created"; \
	echo ""; \
	echo "Copying server files..."; \
	rsync -a --exclude='htmlcov' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='node_modules' --exclude='.venv' backend/ "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/backend/"; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/dist/ "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/frontend/dist/"; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/public/ "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/frontend/public/"; \
	cp -r alembic "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/"; \
	cp alembic.ini "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/"; \
	cp requirements.txt "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/"; \
	cp -r config "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/" 2>/dev/null || true; \
	cp -r scripts "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/" 2>/dev/null || true; \
	echo "✓ Server files copied"; \
	echo ""; \
	echo "Copying configuration files..."; \
	cp installer/netbsd/sysmanage.yaml.example "$$PACKAGE_ROOT/usr/pkg/etc/sysmanage/"; \
	cp installer/netbsd/sysmanage.rc "$$PACKAGE_ROOT/usr/pkg/share/examples/rc.d/sysmanage"; \
	cp installer/netbsd/sysmanage-nginx.conf "$$PACKAGE_ROOT/usr/pkg/share/examples/sysmanage/"; \
	chmod +x "$$PACKAGE_ROOT/usr/pkg/share/examples/rc.d/sysmanage"; \
	echo "✓ Configuration files copied"; \
	echo ""; \
	echo "Copying SBOM..."; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/doc/sysmanage/sbom"; \
	if [ -f sbom/backend-sbom.json ]; then \
		cp sbom/backend-sbom.json "$$PACKAGE_ROOT/usr/pkg/share/doc/sysmanage/sbom/"; \
	fi; \
	if [ -f sbom/frontend-sbom.json ]; then \
		cp sbom/frontend-sbom.json "$$PACKAGE_ROOT/usr/pkg/share/doc/sysmanage/sbom/"; \
	fi; \
	echo "✓ SBOM copied"; \
	echo ""; \
	echo "Copying package metadata files..."; \
	cp installer/netbsd/+INSTALL "$$BUILD_DIR/"; \
	cp installer/netbsd/+DESC "$$BUILD_DIR/"; \
	cp installer/netbsd/+COMMENT "$$BUILD_DIR/"; \
	cp installer/netbsd/+BUILD_INFO "$$BUILD_DIR/"; \
	chmod +x "$$BUILD_DIR/+INSTALL"; \
	echo "✓ Metadata files copied"; \
	echo ""; \
	echo "Creating packing list with dependencies..."; \
	{ \
		echo "@name sysmanage-$$VERSION"; \
		echo "@comment SysManage Server - Centralized system management server for NetBSD"; \
		echo "@pkgdep python312>=3.12"; \
		echo "@pkgdep py312-pip"; \
		echo "@pkgdep postgresql16-server>=16.0"; \
		echo "@pkgdep nginx>=1.24"; \
		cd "$$PACKAGE_ROOT" && find . -type f -o -type l | sed 's,^\./,,'; \
		cd "$$PACKAGE_ROOT" && find . -type d | sed 's,^\./,,' | grep -v '^\.' | sed 's,^,@dirrm ,'; \
	} | sort -u > "$$BUILD_DIR/+CONTENTS"; \
	echo "✓ Packing list created with dependencies"; \
	echo ""; \
	echo "Building package with pkg_create..."; \
	pkg_create \
		-B "$$BUILD_DIR/+BUILD_INFO" \
		-c "$$BUILD_DIR/+COMMENT" \
		-d "$$BUILD_DIR/+DESC" \
		-I "$$BUILD_DIR/+INSTALL" \
		-f "$$BUILD_DIR/+CONTENTS" \
		-p "$$PACKAGE_ROOT" \
		"$$BUILD_DIR/sysmanage-$$VERSION.tgz"; \
	if [ $$? -eq 0 ]; then \
		PACKAGE_FILE="sysmanage-$$VERSION.tgz"; \
		if [ -f "$$BUILD_DIR/$$PACKAGE_FILE" ]; then \
			mkdir -p "$$OUTPUT_DIR"; \
			mv "$$BUILD_DIR/$$PACKAGE_FILE" "$$OUTPUT_DIR/"; \
			echo ""; \
			echo "✓ NetBSD package created successfully: $$OUTPUT_DIR/$$PACKAGE_FILE"; \
			echo ""; \
			echo "Installation commands:"; \
			echo "  sudo pkg_add $$OUTPUT_DIR/$$PACKAGE_FILE"; \
			echo "  sudo cp /usr/pkg/share/examples/rc.d/sysmanage /etc/rc.d/"; \
			echo "  sudo sh -c 'echo sysmanage=YES >> /etc/rc.conf'"; \
			echo "  sudo /etc/rc.d/sysmanage start"; \
			echo ""; \
		else \
			echo "ERROR: Package file not found after build: $$BUILD_DIR/$$PACKAGE_FILE"; \
			exit 1; \
		fi; \
	else \
		echo "ERROR: pkg_create command failed"; \
		exit 1; \
	fi

# SBOM (Software Bill of Materials) generation target
sbom:
	@echo "=================================================="
	@echo "Generating Software Bill of Materials (CycloneDX)"
	@echo "=================================================="
	@echo ""
	@echo "Creating SBOM output directory..."
	@mkdir -p sbom
	@echo "✓ Directory created: ./sbom/"
	@echo ""
	@echo "Checking for CycloneDX tools..."
	@set -e; \
	if ! python3 -c "import cyclonedx_py" 2>/dev/null; then \
		echo "Installing cyclonedx-bom for Python..."; \
		python3 -m pip install cyclonedx-bom --quiet; \
		echo "✓ cyclonedx-bom installed"; \
	else \
		echo "✓ cyclonedx-bom already installed"; \
	fi
	@echo "✓ cyclonedx-npm will be auto-installed via npx if needed"
	@echo ""
	@echo "Generating Python SBOM from requirements.txt..."
	@set -e; \
	python3 -m cyclonedx_py requirements \
		requirements.txt \
		--of JSON \
		-o sbom/backend-sbom.json
	@echo "✓ Python SBOM generated: sbom/backend-sbom.json"
	@echo ""
	@echo "Generating Node.js SBOM from frontend/package.json..."
	@cd frontend && npx --yes @cyclonedx/cyclonedx-npm \
		--output-format JSON \
		--output-file ../sbom/frontend-sbom.json \
		--ignore-npm-errors
	@echo "✓ Node.js SBOM generated: sbom/frontend-sbom.json"
	@echo ""
	@echo "=================================================="
	@echo "SBOM Generation Complete!"
	@echo "=================================================="
	@echo ""
	@echo "Generated files:"
	@ls -lh sbom/*.json
	@echo ""
	@echo "You can view these files with:"
	@echo "  cat sbom/backend-sbom.json | jq ."
	@echo "  cat sbom/frontend-sbom.json | jq ."
	@echo ""
	@echo "Or upload them to vulnerability scanning tools that support CycloneDX format."
