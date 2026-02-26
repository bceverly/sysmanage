# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test test-python test-vite test-ui test-playwright test-e2e test-performance lint lint-python lint-typescript security security-full security-python security-frontend security-secrets security-upgrades sonarqube-scan install-sonar-scanner clean build setup install-dev migrate help start stop start-openbao stop-openbao status-openbao start-telemetry stop-telemetry status-telemetry installer installer-deb installer-alpine installer-freebsd installer-macos installer-msi installer-msi-x64 installer-msi-arm64 installer-msi-all sbom snap snap-clean snap-install snap-uninstall deploy-check-deps checksums release-notes deploy-launchpad deploy-obs deploy-copr deploy-snap deploy-docs-repo release-local

# Default target
help:
	@echo "SysManage Server - Available targets:"
	@echo "  make start         - Start SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make stop          - Stop SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make test          - Run all tests (Python + TypeScript + UI integration + Performance)"
	@echo "  make test-python   - Run Python backend tests only"
	@echo "  make test-vite     - Run Vite/TypeScript frontend tests only"
	@echo "  make test-ui       - Run Selenium UI tests (BSD fallback only)"
	@echo "  make test-e2e      - Run frontend E2E tests (Playwright TypeScript)"
	@echo "  make test-performance - Run Artillery load tests"
	@echo "  make lint          - Run all linters (Python + TypeScript)"
	@echo "  make lint-python   - Run Python linting only"
	@echo "  make lint-typescript - Run TypeScript linting only"
	@echo "  make security      - Run comprehensive security analysis (all tools)"
	@echo "  make security-full - Run comprehensive security analysis (all tools)"
	@echo "  make security-python - Run Python security scanning (Bandit + Safety)"
	@echo "  make security-frontend - Run frontend security scanning (ESLint)"
	@echo "  make security-secrets - Run secrets detection"
	@echo "  make security-upgrades - Check for security package upgrades"
	@echo "  make sonarqube-scan - Run SonarQube/SonarCloud analysis"
	@echo "  make install-sonar-scanner - Install SonarQube scanner locally"
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
	@echo "  make installer-alpine  - Build Alpine .apk packages via Docker (explicit)"
	@echo "  make installer-rpm-centos - Build CentOS/RHEL/Fedora .rpm package (explicit)"
	@echo "  make installer-rpm-opensuse - Build OpenSUSE/SLES .rpm package with vendor deps (explicit)"
	@echo "  make installer-openbsd - Build OpenBSD port tarball (explicit)"
	@echo "  make snap              - Build Snap package (strict confinement, core22, Python 3.10)"
	@echo "  make snap-clean        - Clean snap build artifacts"
	@echo "  make snap-install      - Install snap package locally for testing"
	@echo "  make snap-uninstall    - Uninstall snap package"
	@echo "  make sbom              - Generate Software Bill of Materials (CycloneDX format)"
	@echo ""
	@echo "Deploy targets (local build & publish):"
	@echo "  make deploy-check-deps - Verify deployment tools are installed"
	@echo "  make checksums         - Generate SHA256 checksums for packages in installer/dist/"
	@echo "  make release-notes     - Generate release notes markdown"
	@echo "  make deploy-launchpad  - Build & upload source packages to Launchpad PPA"
	@echo "  make deploy-obs        - Upload to openSUSE Build Service"
	@echo "  make deploy-copr       - Build SRPM & upload to Fedora Copr"
	@echo "  make deploy-snap       - Build and publish snap to Snap Store"
	@echo "  make deploy-docs-repo  - Stage packages into local sysmanage-docs repo"
	@echo "  make release-local     - Full release pipeline with interactive confirmation"
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
	@if [ "$$(uname -s)" = "Darwin" ]; then \
		echo "[INFO] macOS detected - checking for packaging tools..."; \
		command -v pkgbuild >/dev/null 2>&1 || { \
			echo "[WARNING] pkgbuild not found - install with: xcode-select --install"; \
		}; \
		command -v productbuild >/dev/null 2>&1 || { \
			echo "[WARNING] productbuild not found - install with: xcode-select --install"; \
		}; \
		if command -v pkgbuild >/dev/null 2>&1 && command -v productbuild >/dev/null 2>&1; then \
			echo "✓ All macOS packaging tools available"; \
		fi; \
		$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
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
ifdef OPENBAO_BIN
	@echo "[OK] OPENBAO_BIN is set to $(OPENBAO_BIN), skipping install-openbao.py"
else
	@$(PYTHON) scripts/install-openbao.py
endif
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
		echo "[INFO] Checking for LXD..."; \
		if ! snap list 2>/dev/null | grep -q lxd; then \
			echo "LXD not found - installing..."; \
			echo "Running: sudo snap install lxd"; \
			sudo snap install lxd || { \
				echo "[WARNING] Could not install LXD. Run manually: sudo snap install lxd"; \
			}; \
		else \
			echo "✓ LXD already installed"; \
		fi; \
		echo "[INFO] Configuring LXD..."; \
		sudo lxd init --auto 2>/dev/null || true; \
		echo "[INFO] Adding /dev/random, /dev/urandom, and /dev/zero to LXD profiles..."; \
		lxc profile device show default | grep -q "random:" || { \
			lxc profile device add default random unix-char path=/dev/random source=/dev/random || \
			echo "[WARNING] Could not add /dev/random to LXD profile. Run manually: lxc profile device add default random unix-char path=/dev/random source=/dev/random"; \
		}; \
		lxc profile device show default | grep -q "urandom:" || { \
			lxc profile device add default urandom unix-char path=/dev/urandom source=/dev/urandom || \
			echo "[WARNING] Could not add /dev/urandom to LXD profile. Run manually: lxc profile device add default urandom unix-char path=/dev/urandom source=/dev/urandom"; \
		}; \
		lxc profile device show default | grep -q "zero:" || { \
			lxc profile device add default zero unix-char path=/dev/zero source=/dev/zero || \
			echo "[WARNING] Could not add /dev/zero to LXD profile. Run manually: lxc profile device add default zero unix-char path=/dev/zero source=/dev/zero"; \
		}; \
		echo "✓ LXD configured for snapcraft"; \
		if ! groups | grep -q lxd; then \
			echo ""; \
			echo "=============================================="; \
			echo "IMPORTANT: Adding your user to the lxd group"; \
			echo "=============================================="; \
			sudo usermod -aG lxd $$USER || { \
				echo "[WARNING] Could not add user to lxd group. Run manually: sudo usermod -aG lxd $$USER"; \
			}; \
			echo ""; \
			echo "✓ You have been added to the lxd group"; \
			echo ""; \
			echo "IMPORTANT: You MUST log out and log back in for this to take effect!"; \
			echo "          After logging back in, you can run 'make snap' to build snaps."; \
			echo ""; \
		else \
			echo "✓ User already in lxd group"; \
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
	@echo ""
	@echo "=== Optional: SonarQube/SonarCloud Setup ==="
	@echo "For code quality scanning with 'make sonarqube-scan', choose one option:"
	@echo ""
	@echo "  1. SonarCloud (recommended for CI/CD):"
	@echo "     - Sign up at https://sonarcloud.io and import this project"
	@echo "     - Generate a token and add to your environment:"
	@echo "       export SONAR_TOKEN=your_token_here"
	@echo ""
	@echo "  2. Local SonarQube (Docker auto-start):"
	@echo "     - Just run 'make sonarqube-scan' with Docker installed"
	@echo "     - A temporary SonarQube container will start automatically"
	@echo ""
	@echo "  3. Install scanner locally: make install-sonar-scanner"
	@echo ""
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
	@$(PYTHON) -m pylint backend/ --rcfile=.pylintrc
else
	@$(PYTHON) -m pylint backend/ --rcfile=.pylintrc
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

# SonarQube/SonarCloud scan
sonarqube-scan: $(VENV_ACTIVATE)
	@echo "=== SonarQube/SonarCloud Scan ==="
	@if ! command -v sonar-scanner >/dev/null 2>&1; then \
		echo "ERROR: sonar-scanner not found. Install with: make install-sonar-scanner"; \
		echo "Or download from: https://docs.sonarqube.org/latest/analyzing-source-code/scanners/sonarscanner/"; \
		exit 1; \
	fi
	@if [ ! -f sonar-project.properties ]; then \
		echo "ERROR: sonar-project.properties not found"; \
		exit 1; \
	fi
	@echo "Running SonarQube scanner..."
	@if [ -n "$$SONAR_TOKEN" ]; then \
		echo "Using SonarCloud with SONAR_TOKEN..."; \
		sonar-scanner -Dsonar.host.url=https://sonarcloud.io -Dsonar.token=$$SONAR_TOKEN; \
	elif [ -n "$$SONAR_HOST_URL" ]; then \
		echo "Using custom SonarQube server at $$SONAR_HOST_URL..."; \
		sonar-scanner -Dsonar.host.url=$$SONAR_HOST_URL; \
	elif curl -s --connect-timeout 2 http://localhost:9000/api/system/status >/dev/null 2>&1; then \
		echo "Found local SonarQube server at localhost:9000..."; \
		sonar-scanner -Dsonar.host.url=http://localhost:9000; \
	elif command -v docker >/dev/null 2>&1; then \
		echo "No SonarQube server found. Starting temporary Docker container..."; \
		docker run -d --name sonarqube-temp -p 9000:9000 sonarqube:lts-community || true; \
		echo "Waiting for SonarQube to start (this may take 1-2 minutes)..."; \
		for i in $$(seq 1 60); do \
			if curl -s --connect-timeout 2 http://localhost:9000/api/system/status 2>/dev/null | grep -q '"status":"UP"'; then \
				echo "SonarQube is ready!"; \
				break; \
			fi; \
			if [ $$i -eq 60 ]; then \
				echo "ERROR: SonarQube failed to start. Check: docker logs sonarqube-temp"; \
				exit 1; \
			fi; \
			sleep 2; \
		done; \
		sonar-scanner -Dsonar.host.url=http://localhost:9000; \
		echo "Note: SonarQube container 'sonarqube-temp' is still running."; \
		echo "Stop with: docker stop sonarqube-temp && docker rm sonarqube-temp"; \
	else \
		echo ""; \
		echo "ERROR: No SonarQube server available."; \
		echo ""; \
		echo "Options:"; \
		echo "  1. Use SonarCloud (recommended):"; \
		echo "     - Sign up at https://sonarcloud.io"; \
		echo "     - Import this project"; \
		echo "     - Generate a token and run: export SONAR_TOKEN=your_token"; \
		echo ""; \
		echo "  2. Start local SonarQube with Docker:"; \
		echo "     docker run -d --name sonarqube -p 9000:9000 sonarqube:lts-community"; \
		echo ""; \
		echo "  3. Install Docker to enable automatic local scanning"; \
		echo ""; \
		exit 1; \
	fi
	@echo "[OK] SonarQube scan completed"

# Install SonarQube scanner (helper target)
install-sonar-scanner:
	@echo "=== Installing SonarQube Scanner ==="
	@case "$$(uname -s)" in \
		Linux) \
			if command -v apt-get >/dev/null 2>&1; then \
				echo "Installing via apt..."; \
				sudo apt-get update && sudo apt-get install -y unzip; \
			fi; \
			echo "Downloading SonarScanner..."; \
			curl -sSL -o /tmp/sonar-scanner.zip https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip; \
			unzip -o /tmp/sonar-scanner.zip -d /tmp/; \
			sudo mv /tmp/sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner; \
			sudo ln -sf /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner; \
			rm /tmp/sonar-scanner.zip; \
			;; \
		Darwin) \
			if command -v brew >/dev/null 2>&1; then \
				brew install sonar-scanner; \
			else \
				echo "Install Homebrew first, then run: brew install sonar-scanner"; \
				exit 1; \
			fi; \
			;; \
		*) \
			echo "Please install sonar-scanner manually from:"; \
			echo "https://docs.sonarqube.org/latest/analyzing-source-code/scanners/sonarscanner/"; \
			exit 1; \
			;; \
	esac
	@echo "[OK] SonarScanner installed"

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
	@set OTEL_ENABLED=false && $(PYTHON) -m pytest tests/ --ignore=tests/ui/ -v --tb=short -n auto --dist=loadfile --cov=backend --cov-report=term-missing --cov-report=html
else
	@OTEL_ENABLED=false $(PYTHON) -m pytest tests/ --ignore=tests/ui/ -v --tb=short -n auto --dist=loadfile --cov=backend --cov-report=term-missing --cov-report=html
endif
	@echo "[OK] Python tests completed"

# TypeScript/React tests
test-typescript:
	@echo "=== Running TypeScript/React Tests ==="
	@cd frontend && npm run test:coverage
	@echo "[OK] TypeScript tests completed"

# UI integration tests (Selenium fallback for BSD systems where Playwright isn't available)
# On non-BSD systems, use 'make test-e2e' instead for the TypeScript Playwright tests
test-ui: $(VENV_ACTIVATE)
ifeq ($(OS),Windows_NT)
	@echo "[SKIP] Use 'make test-e2e' for Playwright E2E tests on Windows"
else
	@if [ "$(shell uname -s)" = "OpenBSD" ] || [ "$(shell uname -s)" = "FreeBSD" ] || [ "$(shell uname -s)" = "NetBSD" ]; then \
		echo "=== Running UI Integration Tests (Selenium) ==="; \
		echo "[INFO] Using Selenium fallback on BSD systems (OpenBSD/FreeBSD/NetBSD)"; \
		OTEL_ENABLED=false PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_login_selenium.py tests/ui/test_hosts_selenium.py tests/ui/test_updates_selenium.py --confcutdir=tests/ui -p tests.ui.conftest_selenium -v --tb=short; \
		echo "[OK] Selenium UI integration tests completed"; \
	else \
		echo "[SKIP] Use 'make test-e2e' for Playwright E2E tests on $(shell uname -s)"; \
	fi
endif

# Playwright tests only (deprecated - use test-e2e instead)
test-playwright:
	@echo "[DEPRECATED] 'make test-playwright' is deprecated. Use 'make test-e2e' instead."
	@$(MAKE) test-e2e

# Performance testing with Artillery (browser performance tests are now in test-e2e via performance.spec.ts)
test-performance: $(VENV_ACTIVATE)
	@echo "=== Running Performance Tests (Artillery) ==="
ifeq ($(OS),Windows_NT)
	@echo "[INFO] Running Artillery load tests for backend API..."
	@where artillery >nul 2>nul || ( \
		echo "[ERROR] Artillery not found. Installing..." && \
		npm install -g artillery@latest \
	)
	@echo "[INFO] Running Artillery load tests against http://localhost:8001..."
	@echo "[NOTE] Ensure the SysManage server is running on port 8001"
	@artillery run artillery.yml --output artillery-report.json
	@if exist artillery-report.json ( \
		artillery report artillery-report.json --output artillery-report.html && \
		echo "[INFO] Artillery report generated: artillery-report.html" \
	)
	@echo "[INFO] Running performance regression analysis..."
	@$(PYTHON) scripts/performance_regression_check.py
else
	@if [ "$(shell uname -s)" = "OpenBSD" ] || [ "$(shell uname -s)" = "FreeBSD" ] || [ "$(shell uname -s)" = "NetBSD" ]; then \
		echo "[SKIP] Artillery not supported on $(shell uname -s) - performance tests skipped"; \
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
		artillery run artillery.yml --output artillery-report.json; \
		if [ -f artillery-report.json ]; then \
			artillery report artillery-report.json --output artillery-report.html; \
			echo "[INFO] Artillery report generated: artillery-report.html"; \
		fi; \
		echo "[INFO] Running performance regression analysis..."; \
		$(PYTHON) scripts/performance_regression_check.py; \
	fi
endif
	@echo "[OK] Performance testing completed"
	@echo "[INFO] Browser performance tests are included in 'make test-e2e' (performance.spec.ts)"

# Vite tests only (alias for test-typescript)
test-vite: test-typescript

# Frontend E2E tests (Playwright TypeScript tests in frontend/e2e/)
# Automatically starts backend + frontend on port 5173, runs tests, then stops everything
test-e2e: $(VENV_ACTIVATE)
	@echo "=== Running Frontend E2E Tests (Playwright) ==="
ifeq ($(OS),Windows_NT)
	@echo "[INFO] Starting backend API server..."
	@start /B $(PYTHON) -m backend.main > logs\backend-e2e.log 2>&1
	@echo "[INFO] Waiting for backend to be ready..."
	@powershell -Command "Start-Sleep -Seconds 5"
	@echo "[INFO] Starting frontend dev server on port 5173..."
	@cd frontend && set VITE_PORT=5173 && set FORCE_HTTP=true && start /B npm start > ..\logs\frontend-e2e.log 2>&1
	@echo "[INFO] Waiting for frontend to be ready..."
	@powershell -Command "for ($$i=1; $$i -le 20; $$i++) { try { Invoke-WebRequest -Uri http://localhost:5173 -TimeoutSec 2 -UseBasicParsing | Out-Null; Write-Host '[INFO] Frontend ready!'; break } catch { Write-Host '[INFO] Waiting...'; Start-Sleep -Seconds 2 } }"
	@echo "[INFO] Running E2E tests..."
	@cd frontend && npm run test:e2e & set E2E_EXIT=%%ERRORLEVEL%%
	@echo "[INFO] Stopping servers..."
	@taskkill /F /FI "WINDOWTITLE eq *vite*" 2>nul || echo.
	@taskkill /F /FI "WINDOWTITLE eq *python*" 2>nul || echo.
	@if %%E2E_EXIT%% neq 0 exit /b %%E2E_EXIT%%
else
	@if [ "$(shell uname -s)" = "OpenBSD" ] || [ "$(shell uname -s)" = "FreeBSD" ] || [ "$(shell uname -s)" = "NetBSD" ]; then \
		echo "[SKIP] Playwright E2E tests not supported on $(shell uname -s)"; \
	else \
		mkdir -p logs; \
		echo "[INFO] Creating E2E test user..."; \
		. $(VENV_ACTIVATE) && $(PYTHON) scripts/e2e_test_user.py create; \
		echo "[INFO] Checking for port conflicts..."; \
		if lsof -ti:8080 >/dev/null 2>&1; then \
			echo "[INFO] Killing process on port 8080..."; \
			lsof -ti:8080 | xargs kill -9 2>/dev/null || true; \
			sleep 1; \
		fi; \
		if lsof -ti:3000 >/dev/null 2>&1; then \
			echo "[INFO] Killing process on port 3000..."; \
			lsof -ti:3000 | xargs kill -9 2>/dev/null || true; \
			sleep 1; \
		fi; \
		echo "[INFO] Starting backend API server (email disabled for e2e)..."; \
		. $(VENV_ACTIVATE) && SYSMANAGE_DISABLE_EMAIL=true nohup $(PYTHON) -m backend.main > logs/backend-e2e.log 2>&1 & \
		BACKEND_PID=$$!; \
		echo "[INFO] Backend PID: $$BACKEND_PID"; \
		echo "$$BACKEND_PID" > logs/backend-e2e.pid; \
		echo "[INFO] Waiting for backend to be ready on port 8080 (may take up to 2 minutes)..."; \
		BACKEND_READY=0; \
		for i in $$(seq 1 45); do \
			if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then \
				echo "[INFO] Backend is ready!"; \
				BACKEND_READY=1; \
				break; \
			fi; \
			echo "[INFO] Waiting for backend... ($$i/45)"; \
			sleep 2; \
		done; \
		if [ $$BACKEND_READY -eq 0 ]; then \
			echo "[ERROR] Backend failed to start within 90 seconds"; \
			kill $$BACKEND_PID 2>/dev/null || true; \
			exit 1; \
		fi; \
		echo "[INFO] Starting frontend dev server on port 3000..."; \
		cd frontend && FORCE_HTTP=true npm start > ../logs/frontend-e2e.log 2>&1 & \
		VITE_PID=$$!; \
		echo "[INFO] Frontend dev server PID: $$VITE_PID"; \
		echo "$$VITE_PID" > logs/frontend-e2e.pid; \
		echo "[INFO] Waiting for frontend to be ready on port 3000..."; \
		for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
			if curl -s http://localhost:3000 > /dev/null 2>&1; then \
				echo "[INFO] Frontend is ready!"; \
				break; \
			fi; \
			echo "[INFO] Waiting for frontend... ($$i/20)"; \
			sleep 2; \
		done; \
		echo "[INFO] Running E2E tests..."; \
		E2E_EXIT=0; \
		(cd frontend && PLAYWRIGHT_BASE_URL=http://localhost:3000 npm run test:e2e) || E2E_EXIT=$$?; \
		echo "[INFO] Stopping frontend dev server (PID: $$VITE_PID)..."; \
		kill $$VITE_PID 2>/dev/null || true; \
		if [ -f logs/frontend-e2e.pid ]; then kill $$(cat logs/frontend-e2e.pid) 2>/dev/null || true; fi; \
		lsof -ti:3000 | xargs kill -9 2>/dev/null || true; \
		echo "[INFO] Stopping backend server (PID: $$BACKEND_PID)..."; \
		kill $$BACKEND_PID 2>/dev/null || true; \
		if [ -f logs/backend-e2e.pid ]; then kill $$(cat logs/backend-e2e.pid) 2>/dev/null || true; fi; \
		lsof -ti:8080 | xargs kill -9 2>/dev/null || true; \
		rm -f logs/backend-e2e.pid logs/frontend-e2e.pid; \
		echo "[INFO] Cleaning up E2E test user..."; \
		. $(VENV_ACTIVATE) && $(PYTHON) scripts/e2e_test_user.py delete || true; \
		if [ $$E2E_EXIT -ne 0 ]; then \
			echo "[ERROR] E2E tests failed with exit code $$E2E_EXIT"; \
			exit $$E2E_EXIT; \
		fi; \
	fi
endif
	@echo "[OK] Frontend E2E tests completed"

# Model synchronization check
check-test-models:
	@echo "=== Checking Test Model Synchronization ==="
	@$(PYTHON) scripts/check_test_models.py

# Combined testing
# Note: test-ui only runs on BSD systems (Selenium fallback). On other platforms, test-e2e handles UI tests.
test: test-python test-typescript test-e2e test-performance
	@echo "[OK] All tests completed successfully!"

# Build frontend for production
build:
	@echo "=== Building Frontend ==="
	@echo "Installing Node.js dependencies..."
	@cd frontend && npm ci --legacy-peer-deps
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
ifeq ($(OS),Windows_NT)
	@echo "Windows detected - building .msi package"
	@$(MAKE) installer-msi
else
	@if [ "$$(uname -s)" = "Darwin" ]; then \
		echo "macOS detected - building .pkg package"; \
		$(MAKE) installer-macos; \
	elif [ "$$(uname -s)" = "OpenBSD" ]; then \
		echo "OpenBSD detected - building port tarball"; \
		$(MAKE) installer-openbsd; \
	elif [ "$$(uname -s)" = "FreeBSD" ]; then \
		echo "FreeBSD detected - building .pkg package"; \
		$(MAKE) installer-freebsd; \
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
endif

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
installer-openbsd: build
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
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	echo "✓ requirements-prod.txt generated"; \
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
	cp requirements-prod.txt "$$TAR_DIR/"; \
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
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	echo "✓ requirements-prod.txt generated"; \
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
	cp requirements-prod.txt "$$TAR_DIR/"; \
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

# FreeBSD .pkg package
installer-freebsd: build
	@echo "=== Building FreeBSD Package ==="
	@echo ""
	@echo "Creating FreeBSD .pkg package for sysmanage..."
	@echo ""
	@CURRENT_DIR=$$(pwd); \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	BUILD_DIR="$$CURRENT_DIR/build/freebsd"; \
	PACKAGE_ROOT="$$BUILD_DIR/package-root"; \
	echo "Determining version from git..."; \
	VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
	if [ -z "$$VERSION" ]; then \
		VERSION="0.9.0"; \
		echo "WARNING: No git tags found, using default version: $$VERSION"; \
	else \
		echo "Building version: $$VERSION"; \
	fi; \
	echo ""; \
	echo "Cleaning build directory..."; \
	rm -rf "$$BUILD_DIR"; \
	mkdir -p "$$PACKAGE_ROOT"; \
	echo "✓ Build directory prepared: $$BUILD_DIR"; \
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
	echo "Copying and updating manifest..."; \
	MANIFEST_FILE="$$BUILD_DIR/+MANIFEST"; \
	cp "$$CURRENT_DIR/installer/freebsd/+MANIFEST" "$$MANIFEST_FILE"; \
	sed -i.bak "s/^version:.*/version: \"$$VERSION\"/" "$$MANIFEST_FILE"; \
	rm -f "$$MANIFEST_FILE.bak"; \
	echo "✓ Manifest copied and updated to version $$VERSION"; \
	echo ""; \
	echo "Creating package directory structure..."; \
	mkdir -p "$$PACKAGE_ROOT/usr/local/lib/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/local/etc/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/local/etc/rc.d"; \
	mkdir -p "$$PACKAGE_ROOT/usr/local/etc/nginx/conf.d"; \
	mkdir -p "$$PACKAGE_ROOT/usr/local/share/doc/sysmanage/sbom"; \
	echo "✓ Package directories created"; \
	echo ""; \
	echo "Copying backend files..."; \
	cp -R backend "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	cp -R alembic "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	cp alembic.ini "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	cp requirements.txt "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	cp -R config "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	cp -R scripts "$$PACKAGE_ROOT/usr/local/lib/sysmanage/"; \
	echo "✓ Backend files copied"; \
	echo ""; \
	echo "Copying frontend files..."; \
	cp -R frontend/dist "$$PACKAGE_ROOT/usr/local/lib/sysmanage/frontend"; \
	cp -R frontend/public "$$PACKAGE_ROOT/usr/local/lib/sysmanage/frontend-public"; \
	echo "✓ Frontend files copied"; \
	echo ""; \
	echo "Copying configuration files..."; \
	cp installer/freebsd/sysmanage.yaml.example "$$PACKAGE_ROOT/usr/local/etc/sysmanage/"; \
	cp installer/freebsd/sysmanage-nginx.conf "$$PACKAGE_ROOT/usr/local/etc/nginx/conf.d/"; \
	cp installer/freebsd/sysmanage.rc "$$PACKAGE_ROOT/usr/local/etc/rc.d/sysmanage"; \
	chmod +x "$$PACKAGE_ROOT/usr/local/etc/rc.d/sysmanage"; \
	echo "✓ Configuration files copied"; \
	echo ""; \
	echo "Copying SBOM..."; \
	if [ -f sbom/backend-sbom.json ]; then \
		cp sbom/backend-sbom.json "$$PACKAGE_ROOT/usr/local/share/doc/sysmanage/sbom/"; \
	fi; \
	if [ -f sbom/frontend-sbom.json ]; then \
		cp sbom/frontend-sbom.json "$$PACKAGE_ROOT/usr/local/share/doc/sysmanage/sbom/"; \
	fi; \
	echo "✓ SBOM files copied"; \
	echo ""; \
	echo "Building FreeBSD package..."; \
	if command -v pkg >/dev/null 2>&1; then \
		echo "Using native FreeBSD pkg create..."; \
		cd "$$BUILD_DIR" && pkg create -M "$$MANIFEST_FILE" -r "$$PACKAGE_ROOT" -o .; \
	else \
		echo "Using bsdtar for cross-platform build..."; \
		mkdir -p "$$BUILD_DIR/pkg-staging"; \
		cp "$$MANIFEST_FILE" "$$BUILD_DIR/pkg-staging/+MANIFEST"; \
		cd "$$BUILD_DIR/pkg-staging" && bsdtar -czf "../sysmanage-$$VERSION.pkg" --format=pax "+MANIFEST" -C "$$PACKAGE_ROOT" .; \
	fi; \
	if [ $$? -eq 0 ]; then \
		PACKAGE_FILE=$$(ls -1 $$BUILD_DIR/sysmanage-$$VERSION.pkg 2>/dev/null | head -1); \
		if [ -n "$$PACKAGE_FILE" ]; then \
			mkdir -p "$$OUTPUT_DIR"; \
			mv "$$PACKAGE_FILE" "$$OUTPUT_DIR/"; \
			if command -v sha256 >/dev/null 2>&1; then \
				cd "$$OUTPUT_DIR" && sha256 sysmanage-$$VERSION.pkg > sysmanage-$$VERSION.pkg.sha256; \
			else \
				cd "$$OUTPUT_DIR" && sha256sum sysmanage-$$VERSION.pkg > sysmanage-$$VERSION.pkg.sha256; \
			fi; \
			echo ""; \
			echo "✓ FreeBSD package created successfully: $$OUTPUT_DIR/sysmanage-$$VERSION.pkg"; \
			echo ""; \
			echo "Installation commands:"; \
			echo "  sudo pkg add $$OUTPUT_DIR/sysmanage-$$VERSION.pkg"; \
			echo "  sudo sysrc sysmanage_enable=YES"; \
			echo "  sudo sysrc nginx_enable=YES"; \
			echo "  sudo service sysmanage start"; \
			echo "  sudo service nginx start"; \
		else \
			echo "ERROR: Package file not found after creation"; \
			exit 1; \
		fi; \
	else \
		echo "ERROR: Package creation failed"; \
		exit 1; \
	fi

# macOS .pkg package
installer-macos: build
	@echo "=== Building macOS Package ==="
	@echo ""
	@echo "Creating macOS .pkg installer for sysmanage..."
	@echo ""
	@echo "Checking build dependencies..."; \
	command -v pkgbuild >/dev/null 2>&1 || { \
		echo "ERROR: pkgbuild not found."; \
		echo "Install with: xcode-select --install"; \
		exit 1; \
	}; \
	command -v productbuild >/dev/null 2>&1 || { \
		echo "ERROR: productbuild not found."; \
		echo "Install with: xcode-select --install"; \
		exit 1; \
	}; \
	echo "✓ Build tools available"; \
	echo ""; \
	CURRENT_DIR=$$(pwd); \
	OUTPUT_DIR="$$CURRENT_DIR/installer/dist"; \
	BUILD_TEMP="$$OUTPUT_DIR/build-temp-macos"; \
	PAYLOAD_DIR="$$BUILD_TEMP/payload"; \
	SCRIPTS_DIR="$$BUILD_TEMP/scripts"; \
	echo "Determining version from git..."; \
	VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
	if [ -z "$$VERSION" ]; then \
		VERSION="0.9.0"; \
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
	rm -rf "$$BUILD_TEMP"; \
	mkdir -p "$$PAYLOAD_DIR"; \
	mkdir -p "$$SCRIPTS_DIR"; \
	mkdir -p "$$OUTPUT_DIR"; \
	echo "✓ Build directories created"; \
	echo ""; \
	echo "Creating payload structure..."; \
	mkdir -p "$$PAYLOAD_DIR/usr/local/lib/sysmanage"; \
	mkdir -p "$$PAYLOAD_DIR/usr/local/etc/sysmanage"; \
	mkdir -p "$$PAYLOAD_DIR/usr/local/share/doc/sysmanage/sbom"; \
	mkdir -p "$$PAYLOAD_DIR/var/lib/sysmanage"; \
	mkdir -p "$$PAYLOAD_DIR/var/log/sysmanage"; \
	mkdir -p "$$PAYLOAD_DIR/Library/LaunchDaemons"; \
	echo "✓ Payload directories created"; \
	echo ""; \
	echo "Copying backend files..."; \
	rsync -a --exclude='htmlcov' --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='node_modules' --exclude='.venv' backend/ "$$PAYLOAD_DIR/usr/local/lib/sysmanage/backend/"; \
	rsync -a alembic/ "$$PAYLOAD_DIR/usr/local/lib/sysmanage/alembic/"; \
	cp alembic.ini "$$PAYLOAD_DIR/usr/local/lib/sysmanage/"; \
	cp requirements.txt "$$PAYLOAD_DIR/usr/local/lib/sysmanage/"; \
	echo "✓ Backend files copied"; \
	echo ""; \
	echo "Copying frontend files..."; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/dist/ "$$PAYLOAD_DIR/usr/local/lib/sysmanage/frontend/dist/"; \
	rsync -a --exclude='node_modules' --exclude='coverage' frontend/public/ "$$PAYLOAD_DIR/usr/local/lib/sysmanage/frontend/public/"; \
	echo "✓ Frontend files copied"; \
	echo ""; \
	echo "Copying configuration files..."; \
	cp installer/macos/sysmanage.yaml.example "$$PAYLOAD_DIR/usr/local/etc/sysmanage/"; \
	cp installer/macos/sysmanage-nginx.conf "$$PAYLOAD_DIR/usr/local/etc/sysmanage/"; \
	echo "✓ Configuration files copied"; \
	echo ""; \
	echo "Copying SBOM files..."; \
	if [ -f sbom/backend-sbom.json ]; then \
		cp sbom/backend-sbom.json "$$PAYLOAD_DIR/usr/local/share/doc/sysmanage/sbom/"; \
	fi; \
	if [ -f sbom/frontend-sbom.json ]; then \
		cp sbom/frontend-sbom.json "$$PAYLOAD_DIR/usr/local/share/doc/sysmanage/sbom/"; \
	fi; \
	echo "✓ SBOM files copied"; \
	echo ""; \
	echo "Copying LaunchDaemon plist..."; \
	cp installer/macos/com.sysmanage.server.plist "$$PAYLOAD_DIR/Library/LaunchDaemons/com.sysmanage.server.plist"; \
	echo "✓ LaunchDaemon plist copied"; \
	echo ""; \
	echo "Copying postinstall script..."; \
	cp installer/macos/postinstall.sh "$$SCRIPTS_DIR/postinstall"; \
	chmod +x "$$SCRIPTS_DIR/postinstall"; \
	echo "✓ Postinstall script copied"; \
	echo ""; \
	echo "Building component package..."; \
	pkgbuild --root "$$PAYLOAD_DIR" \
		--scripts "$$SCRIPTS_DIR" \
		--identifier com.sysmanage.server \
		--version "$$VERSION" \
		--install-location / \
		"$$BUILD_TEMP/sysmanage-server-component.pkg"; \
	echo "✓ Component package created"; \
	echo ""; \
	echo "Copying distribution XML..."; \
	cp installer/macos/distribution.xml "$$BUILD_TEMP/distribution.xml"; \
	echo "✓ Distribution XML copied"; \
	echo ""; \
	echo "Building final installer package..."; \
	productbuild --distribution "$$BUILD_TEMP/distribution.xml" \
		--package-path "$$BUILD_TEMP" \
		"$$OUTPUT_DIR/sysmanage-$$VERSION-macos.pkg"; \
	echo ""; \
	echo "✓ macOS package created successfully: $$OUTPUT_DIR/sysmanage-$$VERSION-macos.pkg"; \
	echo ""; \
	echo "Installation commands:"; \
	echo "  sudo installer -pkg $$OUTPUT_DIR/sysmanage-$$VERSION-macos.pkg -target /"; \
	echo ""; \
	ls -lh "$$OUTPUT_DIR/sysmanage-$$VERSION-macos.pkg"

# NetBSD .tgz package
installer-netbsd: build
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
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/backend"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/frontend/dist"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/lib/sysmanage/frontend/public"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/etc/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/examples/rc.d"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/examples/sysmanage"; \
	mkdir -p "$$PACKAGE_ROOT/usr/pkg/share/doc/sysmanage/sbom"; \
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
	echo "Building package..."; \
	if command -v pkg_create >/dev/null 2>&1; then \
		echo "Using native NetBSD pkg_create..."; \
		pkg_create \
			-B "$$BUILD_DIR/+BUILD_INFO" \
			-c "$$BUILD_DIR/+COMMENT" \
			-d "$$BUILD_DIR/+DESC" \
			-I "$$BUILD_DIR/+INSTALL" \
			-f "$$BUILD_DIR/+CONTENTS" \
			-p "$$PACKAGE_ROOT" \
			"$$BUILD_DIR/sysmanage-$$VERSION-netbsd.tgz"; \
	else \
		echo "Using tar for cross-platform build..."; \
		mkdir -p "$$BUILD_DIR/pkg-staging"; \
		cp "$$BUILD_DIR/+BUILD_INFO" "$$BUILD_DIR/pkg-staging/"; \
		cp "$$BUILD_DIR/+COMMENT" "$$BUILD_DIR/pkg-staging/"; \
		cp "$$BUILD_DIR/+DESC" "$$BUILD_DIR/pkg-staging/"; \
		cp "$$BUILD_DIR/+INSTALL" "$$BUILD_DIR/pkg-staging/"; \
		cp "$$BUILD_DIR/+CONTENTS" "$$BUILD_DIR/pkg-staging/"; \
		cd "$$BUILD_DIR/pkg-staging" && tar -czf "../sysmanage-$$VERSION-netbsd.tgz" \
			+BUILD_INFO +COMMENT +DESC +INSTALL +CONTENTS \
			-C "$$PACKAGE_ROOT" .; \
	fi; \
	if [ $$? -eq 0 ]; then \
		PACKAGE_FILE="sysmanage-$$VERSION-netbsd.tgz"; \
		if [ -f "$$BUILD_DIR/$$PACKAGE_FILE" ]; then \
			mkdir -p "$$OUTPUT_DIR"; \
			mv "$$BUILD_DIR/$$PACKAGE_FILE" "$$OUTPUT_DIR/"; \
			if command -v sha256 >/dev/null 2>&1; then \
				cd "$$OUTPUT_DIR" && sha256 $$PACKAGE_FILE > $$PACKAGE_FILE.sha256; \
			else \
				cd "$$OUTPUT_DIR" && sha256sum $$PACKAGE_FILE > $$PACKAGE_FILE.sha256; \
			fi; \
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

# Build Alpine .apk packages using Docker (replicates CI/CD Alpine build)
# Supports ALPINE_VERSIONS env var (default: "3.19 3.20 3.21")
installer-alpine:
	@echo "=== Building Alpine .apk Packages via Docker ==="
	@echo ""
	@command -v docker >/dev/null 2>&1 || { \
		echo "ERROR: Docker not found."; \
		echo "Docker is required to build Alpine packages."; \
		echo "Install from: https://docs.docker.com/engine/install/"; \
		exit 1; \
	}
	@echo "✓ Docker available"
	@echo ""
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
	ALPINE_VERSIONS="$${ALPINE_VERSIONS:-3.19 3.20 3.21}"; \
	echo "Alpine versions: $$ALPINE_VERSIONS"; \
	echo ""; \
	mkdir -p installer/dist; \
	for ALPINE_VER in $$ALPINE_VERSIONS; do \
		echo "--- Building for Alpine $$ALPINE_VER ---"; \
		echo ""; \
		docker pull alpine:$$ALPINE_VER; \
		docker run --rm \
			-v "$$(pwd):/workspace" \
			-e VERSION="$$VERSION" \
			alpine:$$ALPINE_VER \
			/workspace/installer/alpine/docker-build.sh; \
		ALPINE_NODOT=$$(echo "$$ALPINE_VER" | tr -d '.'); \
		for pkg in sysmanage-*.apk; do \
			if [ -f "$$pkg" ]; then \
				NEWNAME="sysmanage-$${VERSION}-alpine$${ALPINE_NODOT}.apk"; \
				mv "$$pkg" "installer/dist/$$NEWNAME"; \
				echo "  Created: installer/dist/$$NEWNAME"; \
			fi; \
		done; \
		echo ""; \
	done; \
	echo "✓ Alpine packages built successfully!"; \
	echo ""; \
	ls -lh installer/dist/*alpine*.apk 2>/dev/null || echo "WARNING: No .apk files found in installer/dist/"

# Windows .msi installer (requires Windows with WiX Toolset)
installer-msi: installer-msi-all

# Build Windows .msi installer for x64
installer-msi-x64: build
	@powershell -ExecutionPolicy Bypass -File installer\windows\build-msi.ps1 -Architecture x64

# Build Windows .msi installer for ARM64
installer-msi-arm64: build
	@powershell -ExecutionPolicy Bypass -File installer\windows\build-msi.ps1 -Architecture arm64

# Build Windows .msi installers for both x64 and ARM64
installer-msi-all: build
	@echo ""
	@echo "=================================================="
	@echo "Building Windows installers for all architectures"
	@echo "=================================================="
	@echo ""
	@powershell -ExecutionPolicy Bypass -File installer\windows\build-msi.ps1 -Architecture x64
	@echo ""
	@echo "=================================================="
	@echo ""
	@powershell -ExecutionPolicy Bypass -File installer\windows\build-msi.ps1 -Architecture arm64
	@echo ""
	@echo "=================================================="
	@echo "All Windows installers built!"
	@echo "=================================================="

# Snap package targets
snap:
	@echo ""
	@echo "=================================================="
	@echo "Building Snap package"
	@echo "=================================================="
	@echo ""
	@if ! command -v snapcraft >/dev/null 2>&1; then \
		echo "ERROR: snapcraft not found"; \
		echo "Install with: sudo snap install snapcraft --classic"; \
		exit 1; \
	fi
	@if [ ! -f "installer/snap/snapcraft.yaml" ]; then \
		echo "ERROR: installer/snap/snapcraft.yaml not found"; \
		exit 1; \
	fi
	@echo "Cleaning old LXD containers..."
	@$(MAKE) snap-clean 2>/dev/null || true
	@echo "Generating requirements-prod.txt..."
	@python3 scripts/update-requirements-prod.py
	@echo "Copying snapcraft.yaml and icon to project root..."
	@cp installer/snap/snapcraft.yaml .
	@mkdir -p snap/gui
	@cp installer/snap/gui/icon.svg snap/gui/icon.svg
	@echo "Building snap package..."
	@echo "This will take several minutes due to Python compilation and LXD container setup..."
	@echo ""
	@snapcraft pack --verbose
	@echo ""
	@echo "✓ Snap package built successfully!"
	@echo ""
	@SNAP_FILE=$$(ls -t *.snap 2>/dev/null | head -1); \
	if [ -n "$$SNAP_FILE" ]; then \
		echo "Package: $$SNAP_FILE"; \
		ls -lh "$$SNAP_FILE"; \
		echo ""; \
	fi
	@echo "To install locally:"
	@echo "  make snap-install"
	@echo ""

snap-clean:
	@echo "Cleaning snap build artifacts..."
	@rm -rf parts/ prime/ stage/ *.snap snapcraft.yaml snap/ installer/snap/parts/ installer/snap/prime/ installer/snap/stage/ installer/snap/*.snap
	@echo "Cleaning LXD containers from snapcraft project..."
	@if command -v lxc >/dev/null 2>&1; then \
		lxc --project snapcraft list --format=csv -c n 2>/dev/null | tail -n +1 | while read container; do \
			if [ -n "$$container" ] && [ "$$container" != "{}" ]; then \
				echo "  Deleting container: $$container"; \
				lxc --project snapcraft delete "$$container" --force 2>/dev/null || true; \
			fi; \
		done; \
		echo "✓ LXD containers cleaned"; \
	else \
		echo "✓ LXD not available, skipping container cleanup"; \
	fi
	@echo "✓ Snap build artifacts cleaned"

snap-install:
	@echo "Installing snap package..."
	@if ! ls *.snap 1> /dev/null 2>&1; then \
		echo "ERROR: No snap file found. Run 'make snap' first."; \
		exit 1; \
	fi
	@# Back up existing config if it exists
	@if [ -f /var/snap/sysmanage/common/sysmanage.yaml ]; then \
		echo "Backing up existing configuration..."; \
		sudo cp /var/snap/sysmanage/common/sysmanage.yaml /tmp/sysmanage.yaml.backup; \
		echo "✓ Config backed up to /tmp/sysmanage.yaml.backup"; \
	fi
	@SNAP_FILE=$$(ls -t *.snap | head -1); \
	echo "Installing $$SNAP_FILE..."; \
	sudo snap install --dangerous $$SNAP_FILE
	@# Restore backed up config if it was saved
	@if [ -f /tmp/sysmanage.yaml.backup ]; then \
		echo "Restoring your configuration..."; \
		sudo cp /tmp/sysmanage.yaml.backup /var/snap/sysmanage/common/sysmanage.yaml; \
		sudo rm /tmp/sysmanage.yaml.backup; \
		echo "✓ Config restored"; \
	fi
	@echo ""
	@echo "✓ Snap installed successfully!"
	@echo ""
	@echo "Configuration:"
	@echo "  The snap uses strict confinement and stores data in:"
	@echo "    Config: /var/snap/sysmanage/common/sysmanage.yaml"
	@echo "    Certs:  /var/snap/sysmanage/common/certs/"
	@echo "    Logs:   /var/snap/sysmanage/common/logs/"
	@echo ""
	@echo "  If this is a fresh install, a default config was created."
	@echo "  Edit it with: sudo nano /var/snap/sysmanage/common/sysmanage.yaml"
	@echo ""
	@echo "  Start service: sudo snap start sysmanage"
	@echo "  View logs: sudo snap logs sysmanage"
	@echo ""

snap-uninstall:
	@echo "Uninstalling sysmanage snap..."
	@sudo snap remove sysmanage || echo "Snap not installed or already removed"
	@echo "✓ Snap uninstalled"

# Development environment setup for Windows

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
	@cd frontend && npx cyclonedx-npm \
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

# =============================================================================
# Deploy targets - Local build & publish infrastructure
# =============================================================================

# Version resolution: VERSION env var > git tag > fallback 0.1.0
# Usage: VERSION=1.2.3 make <target>

# Check deployment tool dependencies
deploy-check-deps:
	@echo "=================================================="
	@echo "Checking Deployment Tool Dependencies"
	@echo "=================================================="
	@echo ""
	@MISSING=0; \
	WARN=0; \
	OS_TYPE=$$(uname -s); \
	echo "Detected OS: $$OS_TYPE"; \
	echo ""; \
	\
	echo "=== All Platforms ==="; \
	echo ""; \
	echo "--- Version Detection ---"; \
	if command -v git >/dev/null 2>&1; then \
		echo "  [OK] git"; \
		TAG=$$(git describe --tags --abbrev=0 2>/dev/null || true); \
		if [ -n "$$TAG" ]; then \
			echo "  [OK] Git tag found: $$TAG"; \
		else \
			echo "  [WARN] No git tags found (set VERSION env var to override)"; \
			WARN=1; \
		fi; \
	else \
		echo "  [MISSING] git"; \
		MISSING=1; \
	fi; \
	echo ""; \
	\
	echo "--- Checksums ---"; \
	if command -v sha256sum >/dev/null 2>&1; then \
		echo "  [OK] sha256sum"; \
	elif command -v shasum >/dev/null 2>&1; then \
		echo "  [OK] shasum (will use shasum -a 256)"; \
	elif command -v sha256 >/dev/null 2>&1; then \
		echo "  [OK] sha256 (OpenBSD)"; \
	else \
		echo "  [MISSING] sha256sum / shasum / sha256"; \
		MISSING=1; \
	fi; \
	echo ""; \
	\
	echo "--- SBOM Generation ---"; \
	if python3 -c "import cyclonedx_py" 2>/dev/null; then \
		echo "  [OK] cyclonedx-bom (Python)"; \
	else \
		echo "  [MISSING] cyclonedx-bom"; \
		echo "  Install: pip3 install cyclonedx-bom"; \
		MISSING=1; \
	fi; \
	echo ""; \
	\
	echo "--- Docs Repository ---"; \
	DOCS_REPO="$${DOCS_REPO:-$(HOME)/dev/sysmanage-docs}"; \
	if [ -d "$$DOCS_REPO" ]; then \
		echo "  [OK] sysmanage-docs found at $$DOCS_REPO"; \
	else \
		echo "  [MISSING] sysmanage-docs not found at $$DOCS_REPO"; \
		echo "  Clone it or set DOCS_REPO env var to the correct path"; \
		MISSING=1; \
	fi; \
	echo ""; \
	\
	if [ "$$OS_TYPE" = "Linux" ]; then \
		echo "=== Linux Deploy Targets ==="; \
		echo ""; \
		\
		echo "--- Launchpad PPA (Ubuntu source packages) ---"; \
		for cmd in dch debuild debsign dput gpg; do \
			if command -v $$cmd >/dev/null 2>&1; then \
				echo "  [OK] $$cmd"; \
			else \
				echo "  [MISSING] $$cmd"; \
				MISSING=1; \
			fi; \
		done; \
		if ! command -v dch >/dev/null 2>&1 || ! command -v debuild >/dev/null 2>&1; then \
			echo "  Install: sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools dput-ng gnupg"; \
		fi; \
		if command -v gpg >/dev/null 2>&1; then \
			GPG_KEY=$$(gpg --list-secret-keys --keyid-format LONG 2>/dev/null | grep sec | head -1); \
			if [ -n "$$GPG_KEY" ]; then \
				echo "  [OK] GPG signing key found"; \
			else \
				echo "  [WARN] No GPG signing key found (needed for Launchpad uploads)"; \
				echo "  Import a key or set LAUNCHPAD_GPG_KEY env var"; \
				WARN=1; \
			fi; \
		fi; \
		echo ""; \
		\
		echo "--- OBS (openSUSE Build Service) ---"; \
		if command -v osc >/dev/null 2>&1; then \
			echo "  [OK] osc"; \
		else \
			echo "  [MISSING] osc"; \
			echo "  Install: sudo apt-get install -y osc"; \
			MISSING=1; \
		fi; \
		if [ -f "$$HOME/.config/osc/oscrc" ]; then \
			echo "  [OK] OBS credentials (~/.config/osc/oscrc)"; \
		elif [ -n "$$OBS_USERNAME" ] && [ -n "$$OBS_PASSWORD" ]; then \
			echo "  [OK] OBS credentials (OBS_USERNAME + OBS_PASSWORD env vars)"; \
		else \
			echo "  [WARN] No OBS credentials found"; \
			echo "  Configure ~/.config/osc/oscrc or set OBS_USERNAME + OBS_PASSWORD env vars"; \
			WARN=1; \
		fi; \
		echo ""; \
		\
		echo "--- COPR (Fedora Community Build Service) ---"; \
		for cmd in copr-cli rpmbuild; do \
			if command -v $$cmd >/dev/null 2>&1; then \
				echo "  [OK] $$cmd"; \
			else \
				echo "  [MISSING] $$cmd"; \
				MISSING=1; \
			fi; \
		done; \
		if ! command -v copr-cli >/dev/null 2>&1; then \
			echo "  Install: pip3 install copr-cli"; \
		fi; \
		if ! command -v rpmbuild >/dev/null 2>&1; then \
			echo "  Install: sudo apt-get install -y rpm || sudo dnf install -y rpm-build"; \
		fi; \
		if [ -f "$$HOME/.config/copr" ]; then \
			echo "  [OK] COPR credentials (~/.config/copr)"; \
		elif [ -n "$$COPR_LOGIN" ] && [ -n "$$COPR_API_TOKEN" ] && [ -n "$$COPR_USERNAME" ]; then \
			echo "  [OK] COPR credentials (COPR_LOGIN + COPR_API_TOKEN + COPR_USERNAME env vars)"; \
		else \
			echo "  [WARN] No COPR credentials found"; \
			echo "  Configure ~/.config/copr or set COPR_LOGIN + COPR_API_TOKEN + COPR_USERNAME env vars"; \
			WARN=1; \
		fi; \
		echo ""; \
		\
		echo "--- Snap Store ---"; \
		if command -v snapcraft >/dev/null 2>&1; then \
			echo "  [OK] snapcraft"; \
			if snapcraft whoami >/dev/null 2>&1; then \
				echo "  [OK] Snap Store login active"; \
			else \
				echo "  [WARN] Not logged in to Snap Store"; \
				echo "  Run: snapcraft login"; \
				WARN=1; \
			fi; \
		else \
			echo "  [MISSING] snapcraft"; \
			echo "  Install: sudo snap install snapcraft --classic"; \
			MISSING=1; \
		fi; \
		echo ""; \
		\
		echo "--- Docs Repo Metadata Tools ---"; \
		for cmd in dpkg-scanpackages createrepo_c apt-ftparchive; do \
			if command -v $$cmd >/dev/null 2>&1; then \
				echo "  [OK] $$cmd"; \
			else \
				echo "  [MISSING] $$cmd"; \
				MISSING=1; \
			fi; \
		done; \
		if ! command -v dpkg-scanpackages >/dev/null 2>&1; then \
			echo "  Install: sudo apt-get install -y dpkg-dev"; \
		fi; \
		if ! command -v createrepo_c >/dev/null 2>&1; then \
			echo "  Install: sudo apt-get install -y createrepo-c || sudo dnf install -y createrepo_c"; \
		fi; \
		echo ""; \
		\
		echo "--- Docker (Alpine package builds) ---"; \
		if command -v docker >/dev/null 2>&1; then \
			echo "  [OK] docker"; \
			if docker info >/dev/null 2>&1; then \
				echo "  [OK] Docker daemon accessible"; \
			else \
				echo "  [WARN] Docker installed but daemon not accessible"; \
				echo "  Ensure Docker is running and your user is in the docker group"; \
				WARN=1; \
			fi; \
		else \
			echo "  [MISSING] docker (optional - needed for installer-alpine)"; \
			echo "  Install from: https://docs.docker.com/engine/install/"; \
		fi; \
		echo ""; \
	\
	elif [ "$$OS_TYPE" = "Darwin" ]; then \
		echo "=== macOS Packaging Tools ==="; \
		echo ""; \
		for cmd in pkgbuild productbuild; do \
			if command -v $$cmd >/dev/null 2>&1; then \
				echo "  [OK] $$cmd"; \
			else \
				echo "  [MISSING] $$cmd"; \
				echo "  Install: xcode-select --install"; \
				MISSING=1; \
			fi; \
		done; \
		echo ""; \
		echo "(Launchpad, OBS, COPR, Snap targets are Linux-only -- skipped)"; \
		echo ""; \
	\
	elif echo "$$OS_TYPE" | grep -qE "^(MINGW|MSYS)"; then \
		echo "=== Windows Packaging Tools ==="; \
		echo ""; \
		if command -v powershell >/dev/null 2>&1 || command -v powershell.exe >/dev/null 2>&1; then \
			echo "  [OK] PowerShell"; \
		else \
			echo "  [MISSING] PowerShell"; \
			MISSING=1; \
		fi; \
		if command -v wix >/dev/null 2>&1 || command -v dotnet >/dev/null 2>&1; then \
			echo "  [OK] WiX Toolset / .NET SDK"; \
		else \
			echo "  [WARN] WiX Toolset v4 not detected"; \
			echo "  Install: dotnet tool install --global wix"; \
			WARN=1; \
		fi; \
		echo ""; \
		echo "(Launchpad, OBS, COPR, Snap targets are Linux-only -- skipped)"; \
		echo ""; \
	\
	elif [ "$$OS_TYPE" = "FreeBSD" ]; then \
		echo "=== FreeBSD Packaging Tools ==="; \
		echo ""; \
		if command -v pkg >/dev/null 2>&1; then \
			echo "  [OK] pkg"; \
		else \
			echo "  [MISSING] pkg"; \
			MISSING=1; \
		fi; \
		echo ""; \
		echo "(Launchpad, OBS, COPR, Snap targets are Linux-only -- skipped)"; \
		echo ""; \
	\
	elif [ "$$OS_TYPE" = "NetBSD" ]; then \
		echo "=== NetBSD Packaging Tools ==="; \
		echo ""; \
		if command -v pkg_create >/dev/null 2>&1; then \
			echo "  [OK] pkg_create"; \
		else \
			echo "  [MISSING] pkg_create"; \
			MISSING=1; \
		fi; \
		echo ""; \
		echo "(Launchpad, OBS, COPR, Snap targets are Linux-only -- skipped)"; \
		echo ""; \
	\
	elif [ "$$OS_TYPE" = "OpenBSD" ]; then \
		echo "=== OpenBSD Packaging Tools ==="; \
		echo ""; \
		if command -v tar >/dev/null 2>&1; then \
			echo "  [OK] tar (for port tarball creation)"; \
		else \
			echo "  [MISSING] tar"; \
			MISSING=1; \
		fi; \
		echo ""; \
		echo "(Launchpad, OBS, COPR, Snap targets are Linux-only -- skipped)"; \
		echo ""; \
	\
	else \
		echo "=== Unknown Platform: $$OS_TYPE ==="; \
		echo ""; \
		echo "  No platform-specific checks available."; \
		echo ""; \
	fi; \
	\
	echo "=========================================="; \
	echo "Summary"; \
	echo "=========================================="; \
	echo ""; \
	if [ $$MISSING -eq 0 ] && [ $$WARN -eq 0 ]; then \
		echo "All deployment tools and credentials are configured."; \
	elif [ $$MISSING -eq 0 ]; then \
		echo "All required tools are installed."; \
		echo "Some credentials/config may need attention (see [WARN] items above)."; \
	else \
		echo "Some required tools are missing (see [MISSING] items above)."; \
		if [ $$WARN -ne 0 ]; then \
			echo "Some credentials/config may also need attention (see [WARN] items)."; \
		fi; \
	fi

# Generate SHA256 checksums for all packages in installer/dist/
checksums:
	@echo "=================================================="
	@echo "Generating SHA256 Checksums"
	@echo "=================================================="
	@echo ""
	@if [ ! -d installer/dist ] || [ -z "$$(ls -A installer/dist/ 2>/dev/null)" ]; then \
		echo "ERROR: No packages found in installer/dist/"; \
		echo "Run a package build target first (e.g., make installer-deb)"; \
		exit 1; \
	fi
	@set -e; \
	cd installer/dist; \
	if command -v sha256sum >/dev/null 2>&1; then \
		SHA256CMD="sha256sum"; \
	elif command -v shasum >/dev/null 2>&1; then \
		SHA256CMD="shasum -a 256"; \
	elif command -v sha256 >/dev/null 2>&1; then \
		SHA256CMD="sha256 -r"; \
	else \
		echo "ERROR: No SHA256 tool found (sha256sum, shasum, or sha256)"; \
		exit 1; \
	fi; \
	COUNT=0; \
	for f in *; do \
		[ -f "$$f" ] || continue; \
		case "$$f" in \
			*.sha256) continue ;; \
			*) \
				$$SHA256CMD "$$f" > "$$f.sha256"; \
				echo "  $$f.sha256"; \
				COUNT=$$((COUNT + 1)); \
				;; \
		esac; \
	done; \
	echo ""; \
	echo "Generated $$COUNT checksum files in installer/dist/"

# Generate release notes markdown
release-notes:
	@echo "=================================================="
	@echo "Generating Release Notes"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	mkdir -p installer/dist; \
	NOTES="installer/dist/release-notes-$$VERSION.md"; \
	echo "# SysManage Server v$$VERSION Release Notes" > "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "Release date: $$(date -u +%Y-%m-%d)" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "## Installation" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "### Ubuntu/Debian (APT)" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "# Add the PPA" >> "$$NOTES"; \
	echo "sudo add-apt-repository ppa:bceverly/sysmanage" >> "$$NOTES"; \
	echo "sudo apt update" >> "$$NOTES"; \
	echo "sudo apt install sysmanage" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "### Fedora/RHEL/CentOS (COPR)" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "sudo dnf copr enable bceverly/sysmanage" >> "$$NOTES"; \
	echo "sudo dnf install sysmanage" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "### openSUSE (OBS)" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "# Add the OBS repository for your distribution" >> "$$NOTES"; \
	echo "sudo zypper install sysmanage" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "### Snap" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "sudo snap install sysmanage" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "### macOS" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "# Download the .pkg installer from the releases page" >> "$$NOTES"; \
	echo "sudo installer -pkg sysmanage-$$VERSION-macos.pkg -target /" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "## Verify Downloads" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "SHA256 checksums are provided for all packages. Verify with:" >> "$$NOTES"; \
	echo '```bash' >> "$$NOTES"; \
	echo "sha256sum -c <package-file>.sha256" >> "$$NOTES"; \
	echo '```' >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "## Software Bill of Materials" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "SBOM files in CycloneDX JSON format are available:" >> "$$NOTES"; \
	echo "- \`backend-sbom.json\` - Python backend dependencies" >> "$$NOTES"; \
	echo "- \`frontend-sbom.json\` - Node.js frontend dependencies" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "## Packages" >> "$$NOTES"; \
	echo "" >> "$$NOTES"; \
	echo "| Platform | Package |" >> "$$NOTES"; \
	echo "|----------|---------|" >> "$$NOTES"; \
	if [ -d installer/dist ]; then \
		for f in installer/dist/*; do \
			case "$$f" in \
				*.sha256|*.md) continue ;; \
				*) echo "| $$(basename $$f | sed 's/.*\.//' | tr '[:lower:]' '[:upper:]') | \`$$(basename $$f)\` |" >> "$$NOTES" ;; \
			esac; \
		done; \
	fi; \
	echo "" >> "$$NOTES"; \
	echo "Generated: $$NOTES"

# Deploy to Launchpad PPA
# Usage: LAUNCHPAD_RELEASES="noble jammy" make deploy-launchpad
# Default releases: resolute questing noble jammy
deploy-launchpad:
	@echo "=================================================="
	@echo "Deploy to Launchpad PPA"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	\
	RELEASES="$${LAUNCHPAD_RELEASES:-resolute questing noble jammy}"; \
	echo "Target releases: $$RELEASES"; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	for cmd in dch debuild debsign dput gpg; do \
		command -v $$cmd >/dev/null 2>&1 || { \
			echo "ERROR: $$cmd not found."; \
			echo "Install with: sudo apt-get install -y devscripts debhelper dh-python python3-all python3-setuptools dput-ng gnupg"; \
			exit 1; \
		}; \
	done; \
	echo "Build tools available"; \
	\
	GPG_KEY_ID="$${LAUNCHPAD_GPG_KEY:-}"; \
	if [ -z "$$GPG_KEY_ID" ]; then \
		GPG_KEY_ID=$$(gpg --list-secret-keys --keyid-format LONG 2>/dev/null | grep sec | awk '{print $$2}' | cut -d'/' -f2 | head -1); \
	fi; \
	if [ -z "$$GPG_KEY_ID" ]; then \
		echo "ERROR: No GPG key found."; \
		echo "Either import a GPG key to ~/.gnupg/ or set LAUNCHPAD_GPG_KEY env var"; \
		exit 1; \
	fi; \
	echo "Using GPG key: $$GPG_KEY_ID"; \
	echo ""; \
	\
	echo "Pre-warming GPG agent (you may be prompted for your passphrase)..."; \
	export GPG_TTY=$$(tty); \
	echo "test" | gpg --local-user "$$GPG_KEY_ID" --sign --armor -o /dev/null || \
	{ echo "ERROR: GPG signing failed. Please unlock your key first with:"; \
	  echo "  export GPG_TTY=\$$(tty) && gpg --sign --armor /dev/null"; \
	  exit 1; }; \
	echo "GPG agent ready"; \
	echo ""; \
	\
	if dput --version 2>&1 | grep -q "dput-ng"; then \
		mkdir -p ~/.dput.d/profiles; \
		printf '{\n  "fqdn": "ppa.launchpad.net",\n  "incoming": "~bceverly/ubuntu/sysmanage",\n  "method": "ftp",\n  "allow_unsigned_uploads": false\n}\n' > ~/.dput.d/profiles/launchpad.json; \
	else \
		if ! grep -q '^\[launchpad\]' ~/.dput.cf 2>/dev/null; then \
			printf '\n[launchpad]\nfqdn = ppa.launchpad.net\nmethod = ftp\nincoming = ~bceverly/ubuntu/sysmanage/\nlogin = anonymous\nallow_unsigned_uploads = 0\n' >> ~/.dput.cf; \
		fi; \
	fi; \
	echo "Configured dput for Launchpad PPA"; \
	echo ""; \
	\
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	\
	echo "Building frontend..."; \
	cd frontend && npm ci --legacy-peer-deps && npm run build && cd ..; \
	echo "Frontend build complete"; \
	\
	echo "Generating SBOM files..."; \
	$(MAKE) sbom; \
	echo ""; \
	\
	export DEBFULLNAME="Bryan Everly"; \
	export DEBEMAIL="bryan@theeverlys.com"; \
	\
	for RELEASE in $$RELEASES; do \
		echo "=========================================="; \
		echo "Building source package for Ubuntu $$RELEASE"; \
		echo "Version: $$VERSION"; \
		echo "=========================================="; \
		\
		WORK_DIR="/tmp/sysmanage-$$RELEASE"; \
		rm -rf "$$WORK_DIR"; \
		mkdir -p "$$WORK_DIR"; \
		\
		rsync -a --exclude 'node_modules' --exclude '.git' --exclude '.venv' . "$$WORK_DIR/"; \
		cd "$$WORK_DIR"; \
		\
		if [ -d "installer/ubuntu/debian" ]; then \
			cp -r installer/ubuntu/debian .; \
		else \
			echo "Error: debian directory not found at installer/ubuntu/debian"; \
			exit 1; \
		fi; \
		\
		dch -v "$${VERSION}+ppa1~$${RELEASE}1" -D "$$RELEASE" "New upstream release $${VERSION}"; \
		\
		debuild -S -sa -us -uc -d; \
		\
		cd ..; \
		\
		if [ -n "$$LAUNCHPAD_GPG_PASSPHRASE" ]; then \
			echo "$$LAUNCHPAD_GPG_PASSPHRASE" > "/tmp/gpg-passphrase-$$RELEASE"; \
			debsign --re-sign -p"gpg --batch --yes --passphrase-file /tmp/gpg-passphrase-$$RELEASE" \
				-k"$$GPG_KEY_ID" "sysmanage_$${VERSION}+ppa1~$${RELEASE}1_source.changes"; \
			rm -f "/tmp/gpg-passphrase-$$RELEASE"; \
		else \
			debsign --re-sign -k"$$GPG_KEY_ID" "sysmanage_$${VERSION}+ppa1~$${RELEASE}1_source.changes"; \
		fi; \
		\
		dput launchpad "sysmanage_$${VERSION}+ppa1~$${RELEASE}1_source.changes"; \
		\
		echo "Uploaded to Launchpad PPA for $$RELEASE"; \
		echo ""; \
		\
		cd "$(CURDIR)"; \
	done; \
	\
	echo "=========================================="; \
	echo "All Launchpad uploads complete!"; \
	echo "=========================================="; \
	echo ""; \
	echo "View build status at:"; \
	echo "  https://launchpad.net/~bceverly/+archive/ubuntu/sysmanage"

# Deploy to openSUSE Build Service
deploy-obs:
	@echo "=================================================="
	@echo "Deploy to openSUSE Build Service (OBS)"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	command -v osc >/dev/null 2>&1 || { \
		echo "ERROR: osc not found."; \
		echo "Install with: sudo apt-get install -y osc"; \
		exit 1; \
	}; \
	echo "osc available"; \
	\
	OBS_USER="$${OBS_USERNAME:-}"; \
	if [ -z "$$OBS_USER" ] && [ -f ~/.config/osc/oscrc ]; then \
		OBS_USER=$$(grep "^user" ~/.config/osc/oscrc 2>/dev/null | head -1 | sed 's/^user[[:space:]]*=[[:space:]]*//');\
	fi; \
	if [ -z "$$OBS_USER" ]; then \
		echo "ERROR: OBS credentials not configured."; \
		echo "Either configure ~/.config/osc/oscrc or set OBS_USERNAME and OBS_PASSWORD env vars"; \
		exit 1; \
	fi; \
	\
	if [ -n "$$OBS_USERNAME" ] && [ -n "$$OBS_PASSWORD" ]; then \
		mkdir -p ~/.config/osc; \
		printf '[general]\napiurl = https://api.opensuse.org\n\n[https://api.opensuse.org]\nuser = %s\npass = %s\n' "$$OBS_USERNAME" "$$OBS_PASSWORD" > ~/.config/osc/oscrc; \
		chmod 600 ~/.config/osc/oscrc; \
		echo "OBS credentials configured from env vars"; \
	fi; \
	echo "OBS user: $$OBS_USER"; \
	echo ""; \
	\
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	\
	echo "Building frontend..."; \
	cd frontend && npm ci --legacy-peer-deps && npm run build && cd ..; \
	if [ ! -d "frontend/dist" ]; then \
		echo "ERROR: frontend/dist directory does not exist!"; \
		exit 1; \
	fi; \
	echo "Frontend build complete"; \
	echo ""; \
	\
	OBS_DIR="/tmp/obs-sysmanage"; \
	rm -rf "$$OBS_DIR"; \
	mkdir -p "$$OBS_DIR"; \
	cd "$$OBS_DIR"; \
	\
	echo "Checking out OBS package home:$$OBS_USER/sysmanage"; \
	osc checkout "home:$$OBS_USER/sysmanage"; \
	cd "home:$$OBS_USER/sysmanage"; \
	\
	WORKSPACE="$(CURDIR)"; \
	\
	echo "Copying spec file..."; \
	cp "$$WORKSPACE/installer/opensuse/sysmanage.spec" .; \
	if [ -f "$$WORKSPACE/installer/opensuse/sysmanage-rpmlintrc" ]; then \
		cp "$$WORKSPACE/installer/opensuse/sysmanage-rpmlintrc" .; \
	fi; \
	\
	sed -i "s/^Version:.*/Version:        $$VERSION/" sysmanage.spec; \
	\
	echo "Creating source tarball..."; \
	TAR_NAME="sysmanage-$$VERSION"; \
	mkdir -p "/tmp/$$TAR_NAME"; \
	cp -r "$$WORKSPACE/backend" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/alembic" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/alembic.ini" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/config" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/scripts" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/requirements.txt" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/requirements-prod.txt" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/README.md" "/tmp/$$TAR_NAME/" || touch "/tmp/$$TAR_NAME/README.md"; \
	cp "$$WORKSPACE/LICENSE" "/tmp/$$TAR_NAME/" || touch "/tmp/$$TAR_NAME/LICENSE"; \
	mkdir -p "/tmp/$$TAR_NAME/frontend"; \
	cp -r "$$WORKSPACE/frontend/dist" "/tmp/$$TAR_NAME/frontend/"; \
	cp -r "$$WORKSPACE/frontend/public" "/tmp/$$TAR_NAME/frontend/"; \
	cp "$$WORKSPACE/frontend/package.json" "/tmp/$$TAR_NAME/frontend/" || true; \
	mkdir -p "/tmp/$$TAR_NAME/installer/opensuse"; \
	cp "$$WORKSPACE/installer/opensuse/"*.service "/tmp/$$TAR_NAME/installer/opensuse/" || true; \
	cp "$$WORKSPACE/installer/opensuse/"*.sudoers "/tmp/$$TAR_NAME/installer/opensuse/" || true; \
	cp "$$WORKSPACE/installer/opensuse/"*.example "/tmp/$$TAR_NAME/installer/opensuse/" || true; \
	cp "$$WORKSPACE/installer/opensuse/sysmanage-nginx.conf" "/tmp/$$TAR_NAME/installer/opensuse/" || true; \
	cd /tmp; \
	tar czf "sysmanage-$$VERSION.tar.gz" "$$TAR_NAME/"; \
	echo "Created source tarball: sysmanage-$$VERSION.tar.gz"; \
	\
	echo "Creating vendor tarball (Python 3.11 wheels)..."; \
	rm -rf /tmp/vendor; \
	mkdir -p /tmp/vendor; \
	pip3 download -r "$$WORKSPACE/requirements-prod.txt" -d /tmp/vendor \
		--python-version 311 \
		--platform manylinux2014_x86_64 \
		--platform manylinux_2_17_x86_64 \
		--only-binary=:all:; \
	pip3 download -r "$$WORKSPACE/requirements-prod.txt" -d /tmp/vendor \
		--python-version 311 \
		--no-binary :all: 2>/dev/null || true; \
	cd /tmp; \
	tar czf "sysmanage-vendor-$$VERSION.tar.gz" vendor/; \
	echo "Created vendor tarball: sysmanage-vendor-$$VERSION.tar.gz"; \
	\
	cp "sysmanage-$$VERSION.tar.gz" "$$OBS_DIR/home:$$OBS_USER/sysmanage/"; \
	cp "sysmanage-vendor-$$VERSION.tar.gz" "$$OBS_DIR/home:$$OBS_USER/sysmanage/"; \
	\
	cd "$$OBS_DIR/home:$$OBS_USER/sysmanage"; \
	osc remove *.tar.gz 2>/dev/null || true; \
	osc add "sysmanage-$$VERSION.tar.gz"; \
	osc add "sysmanage-vendor-$$VERSION.tar.gz"; \
	osc add sysmanage.spec 2>/dev/null || true; \
	if [ -f sysmanage-rpmlintrc ]; then \
		osc add sysmanage-rpmlintrc 2>/dev/null || true; \
	fi; \
	\
	echo "Committing to OBS..."; \
	osc commit -m "Release version $$VERSION"; \
	\
	echo ""; \
	echo "=========================================="; \
	echo "Uploaded version $$VERSION to OBS"; \
	echo "=========================================="; \
	echo ""; \
	echo "View build status at:"; \
	echo "  https://build.opensuse.org/package/show/home:$$OBS_USER/sysmanage"

# Deploy to Fedora Copr
deploy-copr:
	@echo "=================================================="
	@echo "Deploy to Fedora Copr"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	for cmd in copr-cli rpmbuild; do \
		command -v $$cmd >/dev/null 2>&1 || { \
			echo "ERROR: $$cmd not found."; \
			if [ "$$cmd" = "copr-cli" ]; then \
				echo "Install with: pip3 install copr-cli"; \
			else \
				echo "Install with: sudo apt-get install -y rpm || sudo dnf install -y rpm-build"; \
			fi; \
			exit 1; \
		}; \
	done; \
	echo "Build tools available"; \
	\
	COPR_USER="$${COPR_USERNAME:-}"; \
	if [ -z "$$COPR_USER" ] && [ -f ~/.config/copr ]; then \
		COPR_USER=$$(grep "^username" ~/.config/copr 2>/dev/null | head -1 | awk '{print $$3}'); \
	fi; \
	if [ -z "$$COPR_USER" ]; then \
		echo "ERROR: Copr credentials not configured."; \
		echo "Either configure ~/.config/copr or set COPR_LOGIN, COPR_API_TOKEN, and COPR_USERNAME env vars"; \
		exit 1; \
	fi; \
	\
	if [ -n "$$COPR_LOGIN" ] && [ -n "$$COPR_API_TOKEN" ] && [ -n "$$COPR_USERNAME" ]; then \
		mkdir -p ~/.config; \
		printf '[copr-cli]\nlogin = %s\nusername = %s\ntoken = %s\ncopr_url = https://copr.fedorainfracloud.org\n' "$$COPR_LOGIN" "$$COPR_USERNAME" "$$COPR_API_TOKEN" > ~/.config/copr; \
		chmod 600 ~/.config/copr; \
		echo "Copr credentials configured from env vars"; \
	fi; \
	echo "Copr user: $$COPR_USER"; \
	echo ""; \
	\
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	\
	echo "Building frontend..."; \
	cd frontend && npm ci --legacy-peer-deps && npm run build && cd ..; \
	echo "Frontend build complete"; \
	echo ""; \
	\
	WORKSPACE="$(CURDIR)"; \
	\
	echo "Creating source tarball..."; \
	TAR_NAME="sysmanage-$$VERSION"; \
	rm -rf "/tmp/$$TAR_NAME"; \
	mkdir -p "/tmp/$$TAR_NAME"; \
	cp -r "$$WORKSPACE/backend" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/alembic" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/alembic.ini" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/requirements.txt" "/tmp/$$TAR_NAME/"; \
	cp "$$WORKSPACE/requirements-prod.txt" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/config" "/tmp/$$TAR_NAME/"; \
	cp -r "$$WORKSPACE/scripts" "/tmp/$$TAR_NAME/"; \
	mkdir -p "/tmp/$$TAR_NAME/frontend"; \
	cp -r "$$WORKSPACE/frontend/dist" "/tmp/$$TAR_NAME/frontend/"; \
	cp -r "$$WORKSPACE/frontend/public" "/tmp/$$TAR_NAME/frontend/"; \
	mkdir -p "/tmp/$$TAR_NAME/installer/centos"; \
	cp "$$WORKSPACE/installer/centos/"*.service "/tmp/$$TAR_NAME/installer/centos/" 2>/dev/null || true; \
	cp "$$WORKSPACE/installer/centos/"*.conf "/tmp/$$TAR_NAME/installer/centos/" 2>/dev/null || true; \
	cp "$$WORKSPACE/installer/centos/"*.example "/tmp/$$TAR_NAME/installer/centos/" 2>/dev/null || true; \
	cp "$$WORKSPACE/README.md" "/tmp/$$TAR_NAME/" || touch "/tmp/$$TAR_NAME/README.md"; \
	cp "$$WORKSPACE/LICENSE" "/tmp/$$TAR_NAME/" || touch "/tmp/$$TAR_NAME/LICENSE"; \
	if [ -d "$$WORKSPACE/sbom" ]; then \
		cp -r "$$WORKSPACE/sbom" "/tmp/$$TAR_NAME/"; \
	fi; \
	cd /tmp; \
	tar czf "sysmanage-$$VERSION.tar.gz" "$$TAR_NAME/"; \
	echo "Created source tarball: sysmanage-$$VERSION.tar.gz"; \
	\
	echo "Creating vendor tarball (Python 3.12 + 3.13 wheels)..."; \
	rm -rf /tmp/vendor; \
	mkdir -p /tmp/vendor; \
	echo "Downloading wheels for Python 3.12 (EPEL 10)..."; \
	pip3 download -r "$$WORKSPACE/requirements-prod.txt" -d /tmp/vendor \
		--python-version 3.12.11 \
		--platform manylinux2014_x86_64 \
		--platform manylinux_2_17_x86_64 \
		--only-binary=:all:; \
	echo "Downloading wheels for Python 3.13 (Fedora 41, 42)..."; \
	pip3 download -r "$$WORKSPACE/requirements-prod.txt" -d /tmp/vendor \
		--python-version 3.13.1 \
		--platform manylinux2014_x86_64 \
		--platform manylinux_2_17_x86_64 \
		--only-binary=:all:; \
	echo "Total wheels: $$(ls -1 /tmp/vendor/*.whl 2>/dev/null | wc -l)"; \
	cd /tmp; \
	tar czf "sysmanage-vendor-$$VERSION.tar.gz" vendor/; \
	echo "Created vendor tarball: sysmanage-vendor-$$VERSION.tar.gz"; \
	\
	echo ""; \
	echo "Copying to rpmbuild directory..."; \
	mkdir -p ~/rpmbuild/SOURCES; \
	cp "/tmp/sysmanage-$$VERSION.tar.gz" ~/rpmbuild/SOURCES/; \
	cp "/tmp/sysmanage-vendor-$$VERSION.tar.gz" ~/rpmbuild/SOURCES/; \
	\
	echo "Creating SRPM..."; \
	cp "$$WORKSPACE/installer/centos/sysmanage.spec" ~/rpmbuild/SOURCES/; \
	cd ~/rpmbuild/SOURCES; \
	sed -i "s/^Version:.*/Version:        $$VERSION/" sysmanage.spec; \
	rpmbuild -bs sysmanage.spec --define "_topdir $$HOME/rpmbuild"; \
	\
	SRPM=$$(find ~/rpmbuild/SRPMS -name "sysmanage-*.src.rpm" | head -1); \
	echo "Created SRPM: $$SRPM"; \
	\
	echo ""; \
	echo "Uploading SRPM to Copr..."; \
	copr-cli build "$$COPR_USER/sysmanage" "$$SRPM"; \
	\
	echo ""; \
	echo "=========================================="; \
	echo "Uploaded version $$VERSION to Copr"; \
	echo "=========================================="; \
	echo ""; \
	echo "View build status at:"; \
	echo "  https://copr.fedorainfracloud.org/coprs/$$COPR_USER/sysmanage/builds/"

# Deploy snap to Snap Store
deploy-snap:
	@echo "=================================================="
	@echo "Deploy Snap to Snap Store"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	command -v snapcraft >/dev/null 2>&1 || { \
		echo "ERROR: snapcraft not found."; \
		echo "Install with: sudo snap install snapcraft --classic"; \
		exit 1; \
	}; \
	\
	echo "Generating requirements-prod.txt..."; \
	python3 scripts/update-requirements-prod.py; \
	\
	echo "Preparing snapcraft files..."; \
	cp installer/snap/snapcraft.yaml .; \
	sed -i "s/^version: git$$/version: $$VERSION/" snapcraft.yaml; \
	mkdir -p snap/gui; \
	cp installer/snap/gui/icon.svg snap/gui/icon.svg; \
	\
	echo "Building snap package..."; \
	snapcraft pack --verbose; \
	\
	SNAP_FILE=$$(ls -t *.snap 2>/dev/null | head -1); \
	if [ -z "$$SNAP_FILE" ]; then \
		echo "ERROR: No snap file produced"; \
		exit 1; \
	fi; \
	echo "Built snap: $$SNAP_FILE"; \
	\
	echo ""; \
	echo "Uploading to Snap Store (stable channel)..."; \
	snapcraft upload --release=stable "$$SNAP_FILE"; \
	\
	echo ""; \
	echo "=========================================="; \
	echo "Published to Snap Store"; \
	echo "=========================================="; \
	echo ""; \
	echo "Install with: sudo snap install sysmanage"; \
	echo "View at: https://snapcraft.io/sysmanage"

# Stage packages into local sysmanage-docs repo (incremental/additive)
# Usage: DOCS_REPO=/path/to/sysmanage-docs make deploy-docs-repo
deploy-docs-repo:
	@echo "=================================================="
	@echo "Stage Packages to sysmanage-docs Repository"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	DOCS_REPO="$${DOCS_REPO:-$(HOME)/dev/sysmanage-docs}"; \
	if [ ! -d "$$DOCS_REPO" ]; then \
		echo "ERROR: sysmanage-docs repo not found at $$DOCS_REPO"; \
		echo "Set DOCS_REPO env var to the correct path"; \
		exit 1; \
	fi; \
	echo "Docs repo: $$DOCS_REPO"; \
	echo ""; \
	\
	STAGED=""; \
	MISSING=""; \
	\
	echo "--- Staging DEB packages ---"; \
	DEB_FILES=$$(ls installer/dist/*.deb 2>/dev/null || true); \
	if [ -n "$$DEB_FILES" ]; then \
		DEB_DIR="$$DOCS_REPO/repo/server/deb/pool/main/$${VERSION}-1"; \
		mkdir -p "$$DEB_DIR"; \
		for f in $$DEB_FILES; do \
			cp "$$f" "$$DEB_DIR/"; \
			echo "  Staged: $$(basename $$f) -> $$DEB_DIR/"; \
		done; \
		STAGED="$$STAGED deb"; \
		if command -v dpkg-scanpackages >/dev/null 2>&1; then \
			echo "  Regenerating DEB metadata..."; \
			cd "$$DOCS_REPO/repo/server/deb"; \
			dpkg-scanpackages pool/main /dev/null > dists/stable/main/binary-amd64/Packages 2>/dev/null || true; \
			gzip -k -f dists/stable/main/binary-amd64/Packages 2>/dev/null || true; \
			if command -v apt-ftparchive >/dev/null 2>&1; then \
				cd dists/stable && apt-ftparchive release . > Release 2>/dev/null || true; \
				cd "$(CURDIR)"; \
			fi; \
			cd "$(CURDIR)"; \
			echo "  DEB metadata updated"; \
		fi; \
	else \
		echo "  No .deb packages found in installer/dist/"; \
		MISSING="$$MISSING deb"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging RPM packages (CentOS/RHEL) ---"; \
	RPM_CENTOS=$$(ls installer/dist/*.el*.rpm installer/dist/*centos*.rpm installer/dist/*fedora*.rpm 2>/dev/null || true); \
	if [ -n "$$RPM_CENTOS" ]; then \
		RPM_DIR="$$DOCS_REPO/repo/server/rpm/centos/$$VERSION"; \
		mkdir -p "$$RPM_DIR"; \
		for f in $$RPM_CENTOS; do \
			cp "$$f" "$$RPM_DIR/"; \
			echo "  Staged: $$(basename $$f) -> $$RPM_DIR/"; \
		done; \
		STAGED="$$STAGED rpm-centos"; \
		if command -v createrepo_c >/dev/null 2>&1; then \
			echo "  Regenerating RPM metadata..."; \
			cd "$$RPM_DIR" && createrepo_c . 2>/dev/null || true; \
			cd "$(CURDIR)"; \
			echo "  RPM metadata updated"; \
		fi; \
	else \
		echo "  No CentOS/RHEL RPM packages found"; \
		MISSING="$$MISSING rpm-centos"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging RPM packages (openSUSE) ---"; \
	RPM_SUSE=$$(ls installer/dist/*suse*.rpm installer/dist/*opensuse*.rpm 2>/dev/null || true); \
	if [ -n "$$RPM_SUSE" ]; then \
		RPM_DIR="$$DOCS_REPO/repo/server/rpm/opensuse/$$VERSION"; \
		mkdir -p "$$RPM_DIR"; \
		for f in $$RPM_SUSE; do \
			cp "$$f" "$$RPM_DIR/"; \
			echo "  Staged: $$(basename $$f) -> $$RPM_DIR/"; \
		done; \
		STAGED="$$STAGED rpm-opensuse"; \
	else \
		echo "  No openSUSE RPM packages found"; \
		MISSING="$$MISSING rpm-opensuse"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging macOS packages ---"; \
	PKG_FILES=$$(ls installer/dist/*.pkg 2>/dev/null || true); \
	if [ -n "$$PKG_FILES" ]; then \
		MAC_DIR="$$DOCS_REPO/repo/server/macos/$$VERSION"; \
		mkdir -p "$$MAC_DIR"; \
		for f in $$PKG_FILES; do \
			cp "$$f" "$$MAC_DIR/"; \
			if [ -f "$$f.sha256" ]; then cp "$$f.sha256" "$$MAC_DIR/"; fi; \
			echo "  Staged: $$(basename $$f) -> $$MAC_DIR/"; \
		done; \
		STAGED="$$STAGED macos"; \
	else \
		echo "  No .pkg packages found"; \
		MISSING="$$MISSING macos"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging Windows packages ---"; \
	MSI_FILES=$$(ls installer/dist/*.msi 2>/dev/null || true); \
	if [ -n "$$MSI_FILES" ]; then \
		WIN_DIR="$$DOCS_REPO/repo/server/windows/$$VERSION"; \
		mkdir -p "$$WIN_DIR"; \
		for f in $$MSI_FILES; do \
			cp "$$f" "$$WIN_DIR/"; \
			if [ -f "$$f.sha256" ]; then cp "$$f.sha256" "$$WIN_DIR/"; fi; \
			echo "  Staged: $$(basename $$f) -> $$WIN_DIR/"; \
		done; \
		STAGED="$$STAGED windows"; \
	else \
		echo "  No .msi packages found"; \
		MISSING="$$MISSING windows"; \
	fi; \
	echo ""; \
	\
	echo "--- Snap packages ---"; \
	echo "  Skipped: snaps are published directly to the Snap Store via 'make deploy-snap'"; \
	echo "  (snap files exceed GitHub's 100MB file size limit)"; \
	echo ""; \
	\
	echo "--- Staging FreeBSD packages ---"; \
	FBSD_FILES=$$(ls installer/dist/*.pkg installer/dist/*freebsd* 2>/dev/null | grep -i freebsd || true); \
	if [ -n "$$FBSD_FILES" ]; then \
		FBSD_DIR="$$DOCS_REPO/repo/server/freebsd/$$VERSION"; \
		mkdir -p "$$FBSD_DIR"; \
		for f in $$FBSD_FILES; do \
			cp "$$f" "$$FBSD_DIR/"; \
			echo "  Staged: $$(basename $$f) -> $$FBSD_DIR/"; \
		done; \
		STAGED="$$STAGED freebsd"; \
	else \
		echo "  No FreeBSD packages found"; \
		MISSING="$$MISSING freebsd"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging OpenBSD packages ---"; \
	OBSD_FILES=$$(ls installer/dist/*openbsd* 2>/dev/null || true); \
	if [ -n "$$OBSD_FILES" ]; then \
		OBSD_DIR="$$DOCS_REPO/repo/server/openbsd/$$VERSION"; \
		mkdir -p "$$OBSD_DIR"; \
		for f in $$OBSD_FILES; do \
			[ -f "$$f" ] || continue; \
			cp "$$f" "$$OBSD_DIR/"; \
			if [ -f "$$f.sha256" ]; then cp "$$f.sha256" "$$OBSD_DIR/"; fi; \
			echo "  Staged: $$(basename $$f) -> $$OBSD_DIR/"; \
		done; \
		STAGED="$$STAGED openbsd"; \
	else \
		echo "  No OpenBSD packages found"; \
		MISSING="$$MISSING openbsd"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging NetBSD packages ---"; \
	NBSD_FILES=$$(ls installer/dist/*netbsd* 2>/dev/null || true); \
	if [ -n "$$NBSD_FILES" ]; then \
		NBSD_DIR="$$DOCS_REPO/repo/server/netbsd/$$VERSION"; \
		mkdir -p "$$NBSD_DIR"; \
		for f in $$NBSD_FILES; do \
			[ -f "$$f" ] || continue; \
			cp "$$f" "$$NBSD_DIR/"; \
			if [ -f "$$f.sha256" ]; then cp "$$f.sha256" "$$NBSD_DIR/"; fi; \
			echo "  Staged: $$(basename $$f) -> $$NBSD_DIR/"; \
		done; \
		STAGED="$$STAGED netbsd"; \
	else \
		echo "  No NetBSD packages found"; \
		MISSING="$$MISSING netbsd"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging Alpine packages ---"; \
	APK_FILES=$$(ls installer/dist/*alpine*.apk 2>/dev/null || true); \
	if [ -n "$$APK_FILES" ]; then \
		APK_DIR="$$DOCS_REPO/repo/server/alpine/$$VERSION"; \
		mkdir -p "$$APK_DIR"; \
		for f in $$APK_FILES; do \
			cp "$$f" "$$APK_DIR/"; \
			if [ -f "$$f.sha256" ]; then cp "$$f.sha256" "$$APK_DIR/"; fi; \
			echo "  Staged: $$(basename $$f) -> $$APK_DIR/"; \
		done; \
		STAGED="$$STAGED alpine"; \
	else \
		echo "  No Alpine .apk packages found"; \
		MISSING="$$MISSING alpine"; \
	fi; \
	echo ""; \
	\
	echo "--- Staging checksums and SBOMs ---"; \
	SHA_FILES=$$(ls installer/dist/*.sha256 2>/dev/null || true); \
	if [ -n "$$SHA_FILES" ]; then \
		echo "  Checksum files will be copied alongside their packages"; \
	fi; \
	if [ -d sbom ]; then \
		SBOM_DIR="$$DOCS_REPO/repo/server/sbom/$$VERSION"; \
		mkdir -p "$$SBOM_DIR"; \
		cp sbom/*.json "$$SBOM_DIR/" 2>/dev/null || true; \
		echo "  Staged SBOM files -> $$SBOM_DIR/"; \
	fi; \
	echo ""; \
	\
	echo "=========================================="; \
	echo "Staging Summary (v$$VERSION)"; \
	echo "=========================================="; \
	echo ""; \
	if [ -n "$$STAGED" ]; then \
		echo "Staged platforms:$$STAGED"; \
	else \
		echo "No packages were staged."; \
	fi; \
	if [ -n "$$MISSING" ]; then \
		echo "Missing platforms:$$MISSING"; \
		echo ""; \
		echo "Run deploy-docs-repo on other machines to stage those platforms."; \
		echo "Each run is additive - existing packages are preserved."; \
	fi; \
	echo ""; \
	echo "When all platforms are staged and GitHub access is restored:"; \
	echo "  cd $$DOCS_REPO"; \
	echo "  git add repo/"; \
	echo "  git commit -m 'Release sysmanage v$$VERSION'"; \
	echo "  git push"

# Full release pipeline with interactive confirmation
release-local:
	@echo "=================================================="
	@echo "SysManage Server - Local Release Pipeline"
	@echo "=================================================="
	@echo ""
	@set -e; \
	if [ -n "$$VERSION" ]; then \
		echo "Using VERSION from environment: $$VERSION"; \
	else \
		VERSION=$$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//'); \
		if [ -z "$$VERSION" ]; then \
			VERSION="0.1.0"; \
			echo "No git tags found, using default version: $$VERSION"; \
		else \
			echo "Using version from git tag: $$VERSION"; \
		fi; \
	fi; \
	echo "Version: $$VERSION"; \
	echo ""; \
	\
	OS_TYPE=$$(uname -s); \
	echo "Detected OS: $$OS_TYPE"; \
	echo ""; \
	echo "This will run the release pipeline for the current platform."; \
	echo "Each step requires confirmation before proceeding."; \
	echo ""; \
	\
	echo "--- Step 1: Build packages for current platform ---"; \
	case "$$OS_TYPE" in \
		Linux) \
			if [ -f /etc/os-release ] && grep -qE "^ID=\"?(opensuse|sles)" /etc/os-release 2>/dev/null; then \
				BUILD_TARGET="installer-rpm-opensuse"; \
			elif [ -f /etc/redhat-release ]; then \
				BUILD_TARGET="installer-rpm-centos"; \
			else \
				BUILD_TARGET="installer-deb"; \
			fi; \
			;; \
		Darwin) \
			BUILD_TARGET="installer-macos"; \
			;; \
		FreeBSD) \
			BUILD_TARGET="installer-freebsd"; \
			;; \
		NetBSD) \
			BUILD_TARGET="installer-netbsd"; \
			;; \
		OpenBSD) \
			BUILD_TARGET="installer-openbsd"; \
			;; \
		MINGW*|MSYS*) \
			BUILD_TARGET="installer-msi-all"; \
			;; \
		*) \
			echo "WARNING: Unknown OS $$OS_TYPE, defaulting to installer-deb"; \
			BUILD_TARGET="installer-deb"; \
			;; \
	esac; \
	printf "Build packages with 'make $$BUILD_TARGET'? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) \
			export VERSION; \
			$(MAKE) $$BUILD_TARGET; \
			;; \
		*) echo "Skipped."; ;; \
	esac; \
	echo ""; \
	\
	echo "--- Step 2: Generate SBOM ---"; \
	printf "Generate SBOM with 'make sbom'? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) $(MAKE) sbom; ;; \
		*) echo "Skipped."; ;; \
	esac; \
	echo ""; \
	\
	echo "--- Step 3: Generate checksums ---"; \
	printf "Generate checksums with 'make checksums'? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) $(MAKE) checksums; ;; \
		*) echo "Skipped."; ;; \
	esac; \
	echo ""; \
	\
	echo "--- Step 4: Generate release notes ---"; \
	printf "Generate release notes with 'make release-notes'? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) export VERSION; $(MAKE) release-notes; ;; \
		*) echo "Skipped."; ;; \
	esac; \
	echo ""; \
	\
	echo "--- Step 5: Stage to docs repo ---"; \
	printf "Stage packages to sysmanage-docs with 'make deploy-docs-repo'? [y/N] "; \
	read REPLY; \
	case "$$REPLY" in \
		[Yy]*) export VERSION; $(MAKE) deploy-docs-repo; ;; \
		*) echo "Skipped."; ;; \
	esac; \
	echo ""; \
	\
	if [ "$$OS_TYPE" = "Linux" ]; then \
		echo "--- Step 6: Deploy to Launchpad ---"; \
		printf "Upload to Launchpad PPA with 'make deploy-launchpad'? [y/N] "; \
		read REPLY; \
		case "$$REPLY" in \
			[Yy]*) export VERSION; $(MAKE) deploy-launchpad; ;; \
			*) echo "Skipped."; ;; \
		esac; \
		echo ""; \
		\
		echo "--- Step 7: Deploy to OBS ---"; \
		printf "Upload to OBS with 'make deploy-obs'? [y/N] "; \
		read REPLY; \
		case "$$REPLY" in \
			[Yy]*) export VERSION; $(MAKE) deploy-obs; ;; \
			*) echo "Skipped."; ;; \
		esac; \
		echo ""; \
		\
		echo "--- Step 8: Deploy to COPR ---"; \
		printf "Upload to COPR with 'make deploy-copr'? [y/N] "; \
		read REPLY; \
		case "$$REPLY" in \
			[Yy]*) export VERSION; $(MAKE) deploy-copr; ;; \
			*) echo "Skipped."; ;; \
		esac; \
		echo ""; \
		\
		echo "--- Step 9: Deploy to Snap Store ---"; \
		printf "Publish snap with 'make deploy-snap'? [y/N] "; \
		read REPLY; \
		case "$$REPLY" in \
			[Yy]*) export VERSION; $(MAKE) deploy-snap; ;; \
			*) echo "Skipped."; ;; \
		esac; \
		echo ""; \
		\
		echo "--- Step 10: Build Alpine packages (requires Docker) ---"; \
		if command -v docker >/dev/null 2>&1; then \
			printf "Build Alpine .apk packages with 'make installer-alpine'? [y/N] "; \
			read REPLY; \
			case "$$REPLY" in \
				[Yy]*) export VERSION; $(MAKE) installer-alpine; ;; \
				*) echo "Skipped."; ;; \
			esac; \
		else \
			echo "  Docker not found, skipping Alpine packages."; \
		fi; \
		echo ""; \
	else \
		echo "(Steps 6-10 skipped: Linux-only deploy targets)"; \
		echo ""; \
	fi; \
	\
	echo "=========================================="; \
	echo "Release pipeline complete for v$$VERSION"; \
	echo "=========================================="; \
	echo ""; \
	echo "Summary:"; \
	echo "  Platform: $$OS_TYPE"; \
	echo "  Version:  $$VERSION"; \
	echo ""; \
	echo "Next steps:"; \
	echo "  - Run 'make release-local' on other machines for additional platforms"; \
	echo "  - When all platforms are done, commit and push sysmanage-docs"
