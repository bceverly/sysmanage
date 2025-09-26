# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test test-python test-vite test-playwright lint lint-python lint-typescript security security-full security-python security-frontend security-secrets security-upgrades clean setup install-dev migrate help start stop start-openbao stop-openbao status-openbao

# Default target
help:
	@echo "SysManage Server - Available targets:"
	@echo "  make start         - Start SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make stop          - Stop SysManage server + OpenBAO (auto-detects shell/platform)"
	@echo "  make test          - Run all tests (Python + TypeScript + UI integration)"
	@echo "  make test-python   - Run Python backend tests only"
	@echo "  make test-vite     - Run Vite/TypeScript frontend tests only"
	@echo "  make test-playwright - Run Playwright UI tests only"
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
	@echo "OpenBSD users: install-dev will check for C tracer dependencies (gcc, py3-cffi)"

# Virtual environment activation
VENV := .venv

# Detect OS and set paths accordingly
ifeq ($(OS),Windows_NT)
    PYTHON := $(VENV)/Scripts/python.exe
    PIP := $(VENV)/Scripts/pip.exe
    VENV_ACTIVATE := $(VENV)/Scripts/activate
else
    PYTHON := $(VENV)/bin/python
    PIP := $(VENV)/bin/pip
    VENV_ACTIVATE := $(VENV)/bin/activate
endif

# Check if virtual environment exists
$(VENV_ACTIVATE):
	@echo "Virtual environment not found. Please create one with:"
	@echo "  python3 -m venv .venv"
ifeq ($(OS),Windows_NT)
	@echo "  .venv\Scripts\activate"
else
	@echo "  source .venv/bin/activate"
endif
	@echo "  pip install -r requirements.txt"
	@exit 1

# Install development dependencies
install-dev: $(VENV_ACTIVATE)
	@echo "Installing Python development dependencies..."
	@$(PIP) install pytest pytest-cov pytest-asyncio pylint black isort bandit safety semgrep
	@echo "Installing requirements.txt (includes Selenium WebDriver)..."
	@$(PIP) install -r requirements.txt
	@echo "Checking for OpenBSD C tracer requirements..."
	@$(PYTHON) scripts/check-openbsd-deps.py
	@echo "Installing OpenBAO for secrets management..."
	@$(PYTHON) scripts/install-openbao.py
	@echo "Setting up WebDriver for screenshots..."
	@$(PYTHON) scripts/install-browsers.py
	@if [ "$(shell uname -s)" != "OpenBSD" ] && [ "$(shell uname -s)" != "FreeBSD" ]; then \
		echo "Installing Playwright browsers..."; \
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
		echo "Skipping Playwright installation on OpenBSD/FreeBSD - using Selenium with system browser"; \
		echo "Installing Selenium WebDriver dependencies for cross-browser testing..."; \
		if [ "$(shell uname -s)" = "OpenBSD" ]; then \
			echo "Installing geckodriver for Firefox support..."; \
			if command -v doas >/dev/null 2>&1; then \
				doas pkg_add geckodriver || echo "Warning: Could not install geckodriver"; \
			elif command -v sudo >/dev/null 2>&1; then \
				sudo pkg_add geckodriver || echo "Warning: Could not install geckodriver"; \
			else \
				echo "Warning: No privilege escalation command found. Please install manually:"; \
				echo "  doas pkg_add geckodriver"; \
			fi; \
		elif [ "$(shell uname -s)" = "FreeBSD" ]; then \
			echo "Installing Firefox and geckodriver for cross-browser testing..."; \
			if command -v sudo >/dev/null 2>&1; then \
				sudo pkg install -y firefox geckodriver || echo "Warning: Could not install Firefox/geckodriver"; \
			else \
				echo "Warning: No privilege escalation command found. Please install manually:"; \
				echo "  sudo pkg install firefox geckodriver"; \
			fi; \
		fi; \
	fi
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
	@where grep >nul 2>nul || (echo "Installing grep via chocolatey (requires admin privileges)..." && powershell -Command "Start-Process powershell -ArgumentList '-Command choco install grep -y' -Verb RunAs -Wait" || echo "Failed to install grep - you may need to run as administrator or install chocolatey first")
endif
ifeq ($(OS),Windows_NT)
	@where eslint >nul 2>nul || (echo "Installing global ESLint..." && npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin)
else
	@if ! command -v eslint >/dev/null 2>&1; then \
		echo "Installing global ESLint..."; \
		npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin; \
	fi
endif

# Database migration target
migrate: $(VENV_ACTIVATE)
	@echo "Running database migrations..."
	@$(PYTHON) -m alembic upgrade head
	@echo "[OK] Database migrations completed"

# Setup target that ensures everything is ready
setup: install-dev
	@echo "Development environment setup complete!"

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
	@$(PYTHON) -m pytest tests/ --ignore=tests/ui/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=html
	@echo "[OK] Python tests completed"

# TypeScript/React tests
test-typescript:
	@echo "=== Running TypeScript/React Tests ==="
	@cd frontend && npm test
	@echo "[OK] TypeScript tests completed"

# UI integration tests
test-ui: $(VENV_ACTIVATE)
	@if [ "$(shell uname -s)" != "OpenBSD" ] && [ "$(shell uname -s)" != "FreeBSD" ]; then \
		echo "=== Running UI Integration Tests (Playwright) ==="; \
		if [ "$(shell uname -s)" = "Darwin" ]; then \
			echo "[INFO] macOS detected - testing Chrome, Firefox, and WebKit/Safari"; \
		else \
			echo "[INFO] Linux/Windows detected - testing Chrome and Firefox"; \
		fi; \
		PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_login_cross_browser.py --confcutdir=tests/ui -p conftest_playwright -v --tb=short; \
		echo "[OK] Playwright UI integration tests completed"; \
	else \
		echo "=== Running UI Integration Tests (Selenium) ==="; \
		echo "[INFO] Using Selenium fallback on OpenBSD/FreeBSD"; \
		PYTHONPATH=tests/ui:$$PYTHONPATH $(PYTHON) -m pytest tests/ui/test_login_selenium.py --confcutdir=tests/ui -p conftest_selenium -v --tb=short; \
		echo "[OK] Selenium UI integration tests completed"; \
	fi

# Playwright tests only (alias for test-ui)
test-playwright: test-ui

# Vite tests only (alias for test-typescript)
test-vite: test-typescript

# Model synchronization check
check-test-models:
	@echo "=== Checking Test Model Synchronization ==="
	@$(PYTHON) scripts/check_test_models.py

# Combined testing
test: test-python test-typescript test-ui
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
	@echo "Starting OpenBAO development server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/start-openbao.ps1 || scripts\start-openbao.cmd
else
	@./scripts/start-openbao.sh
endif
	@echo ""
	@echo "Starting SysManage server..."
ifeq ($(OS),Windows_NT)
	@powershell -ExecutionPolicy Bypass -File scripts/start.ps1 || scripts\start.cmd
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