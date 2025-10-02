# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test test-python test-vite test-playwright test-performance lint lint-python lint-typescript security security-full security-python security-frontend security-secrets security-upgrades clean setup install-dev migrate help start stop start-openbao stop-openbao status-openbao start-telemetry stop-telemetry status-telemetry

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
	@echo "  make install-dev   - Install all development tools (includes Playwright + WebDriver + MSW for testing)"
	@echo "  make migrate       - Run database migrations (alembic upgrade head)"
	@echo "  make check-test-models - Check test model synchronization between conftest files"
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
	@echo "  - OpenBSD: gcc, py3-cffi"
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
	@$(PYTHON) -m pip install --upgrade pip
endif

setup-venv: $(VENV_ACTIVATE)

# Install development dependencies
install-dev: setup-venv
	@echo "Installing Python development dependencies..."
ifeq ($(OS),Windows_NT)
	@$(PYTHON) -m pip install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep
else
	@if [ "$$(uname -s)" = "NetBSD" ]; then \
		echo "[INFO] NetBSD detected - configuring for grpcio build..."; \
		export TMPDIR=/var/tmp && \
		export CFLAGS="-I/usr/pkg/include" && \
		export CXXFLAGS="-std=c++17 -I/usr/pkg/include -fpermissive" && \
		export LDFLAGS="-L/usr/pkg/lib -Wl,-R/usr/pkg/lib" && \
		export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
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
		export CFLAGS="-I/usr/pkg/include" && \
		export CXXFLAGS="-std=c++17 -I/usr/pkg/include -fpermissive" && \
		export LDFLAGS="-L/usr/pkg/lib -Wl,-R/usr/pkg/lib" && \
		export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
		grep -v "^playwright" requirements.txt | $(PYTHON) -m pip install -r /dev/stdin || true; \
		echo "[INFO] Selenium will be used for browser testing on BSD systems"; \
	elif [ "$$(uname -s)" = "OpenBSD" ] || [ "$$(uname -s)" = "FreeBSD" ]; then \
		echo "[INFO] Installing packages except Playwright (not available on BSD systems)..."; \
		grep -v "^playwright" requirements.txt | $(PYTHON) -m pip install -r /dev/stdin || true; \
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
		export CXXFLAGS="-std=c++17 -I/usr/pkg/include -fpermissive" && \
		export LDFLAGS="-L/usr/pkg/lib -Wl,-R/usr/pkg/lib" && \
		export GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_ZLIB=1 && \
		export GRPC_PYTHON_BUILD_SYSTEM_CARES=1 && \
		$(PYTHON) -m pip uninstall -y Pillow && $(PYTHON) -m pip install --no-binary=:all: Pillow; \
		echo "[OK] Pillow rebuilt for NetBSD"; \
		echo "[INFO] NetBSD detected - rebuilding grpcio with GCC 14 for C++ compatibility..."; \
		$(PYTHON) -m pip cache remove grpcio 2>/dev/null || true; \
		$(PYTHON) -m pip uninstall -y grpcio && \
		CC=/usr/pkg/gcc14/bin/gcc \
		CXX=/usr/pkg/gcc14/bin/g++ \
		CFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
		CXXFLAGS="-I/usr/pkg/include -fpermissive -Wno-error" \
		LDFLAGS="-L/usr/pkg/gcc14/lib -Wl,-R/usr/pkg/gcc14/lib -lstdc++" \
		LDSHARED="/usr/pkg/gcc14/bin/g++ -pthread -shared -L/usr/pkg/gcc14/lib -Wl,-R/usr/pkg/gcc14/lib" \
		$(PYTHON) -m pip install --no-binary=:all: grpcio; \
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
	fi
	@echo "Installing telemetry stack (OpenTelemetry + Prometheus)..."
	@sudo $(PYTHON) scripts/install-telemetry.py || echo "[WARNING] Telemetry installation failed - continuing without telemetry"
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
				sudo $(PYTHON) -m playwright install-deps 2>/dev/null || ( \
					echo ""; \
					echo "❌ Playwright automatic dependency installation failed."; \
					echo "   Installing manually..."; \
					echo ""; \
					sudo apt-get update -qq && \
					sudo apt-get install -y \
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
	@cd frontend && npm install --include=optional
	@echo "Ensuring esbuild optional dependencies are installed..."
	@cd frontend && npm uninstall esbuild && npm install esbuild
	@echo "Installing ESLint security plugins..."
	@cd frontend && npm install eslint-plugin-security eslint-plugin-no-unsanitized
	@echo "Setting up MSW (Mock Service Worker) for API mocking..."
	@cd frontend && npm install --save-dev msw
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
else
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov/ .coverage
	@cd frontend && rm -rf coverage/ 2>/dev/null || true
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
		nohup otelcol-contrib --config=config/otel-collector-config.yml > logs/otel-collector.log 2>&1 & echo $$! > logs/otel-collector.pid; \
		echo "OpenTelemetry Collector started (PID: $$(cat logs/otel-collector.pid))"; \
	else \
		echo "[WARNING] otelcol-contrib not found. Run 'make install-telemetry' first."; \
	fi
	@echo "Starting Prometheus..."
	@PROMETHEUS_BIN=""; \
	if [ -f "$$HOME/.local/bin/prometheus" ]; then \
		PROMETHEUS_BIN="$$HOME/.local/bin/prometheus"; \
	elif command -v prometheus >/dev/null 2>&1; then \
		PROMETHEUS_BIN="prometheus"; \
	fi; \
	if [ -n "$$PROMETHEUS_BIN" ]; then \
		mkdir -p data/prometheus; \
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