# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test lint lint-python lint-typescript security clean setup install-dev help

# Default target
help:
	@echo "SysManage Server - Available targets:"
	@echo "  make test          - Run all unit tests (Python + TypeScript)"
	@echo "  make lint          - Run all linters (Python + TypeScript)"
	@echo "  make lint-python   - Run Python linting only"
	@echo "  make lint-typescript - Run TypeScript linting only"
	@echo "  make security      - Run security analysis with Bandit"
	@echo "  make setup         - Install development dependencies"
	@echo "  make clean         - Clean test artifacts and cache"
	@echo "  make install-dev   - Install all development tools"

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
	@$(PIP) install pytest pytest-cov pytest-asyncio pylint black isort bandit
	@echo "Installing TypeScript/React development dependencies..."
	@cd frontend && npm install
	@if ! command -v eslint >/dev/null 2>&1; then \
		echo "Installing global ESLint..."; \
		npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin; \
	fi

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

# Security analysis
security: $(VENV_ACTIVATE)
	@echo "=== Security Analysis ==="
	@echo "Running Bandit security analysis..."
ifeq ($(OS),Windows_NT)
	-@$(PYTHON) -m bandit -r backend/ -f screen -x backend/tests/
else
	@$(PYTHON) -m bandit -r backend/ -f screen -x backend/tests/ || true
endif
	@echo "[OK] Security analysis completed"

# Format Python code (helper target)
format-python: $(VENV_ACTIVATE) clean-whitespace
	@echo "Formatting Python code..."
	@$(PYTHON) -m black backend/ tests/

# Python tests
test-python: $(VENV_ACTIVATE) clean-whitespace
	@echo "=== Running Python Tests ==="
	@$(PYTHON) -m pytest tests/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=html
	@echo "[OK] Python tests completed"

# TypeScript/React tests
test-typescript:
	@echo "=== Running TypeScript/React Tests ==="
	@cd frontend && npm test
	@echo "[OK] TypeScript tests completed"

# Combined testing
test: test-python test-typescript
	@echo "[OK] All tests completed successfully!"

# Clean artifacts
clean:
	@echo "Cleaning test artifacts and cache..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov/ .coverage
	@cd frontend && rm -rf coverage/ 2>/dev/null || true
	@echo "[OK] Clean completed"

# Development server targets (bonus)
run-dev: setup
	@echo "Starting development servers..."
	@./run.sh

stop-dev:
	@echo "Stopping development servers..."
	@./stop.sh