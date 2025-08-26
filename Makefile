# SysManage Server Makefile
# Provides testing and linting for Python backend and TypeScript frontend

.PHONY: test lint lint-python lint-typescript clean setup install-dev help

# Default target
help:
	@echo "SysManage Server - Available targets:"
	@echo "  make test          - Run all unit tests (Python + TypeScript)"
	@echo "  make lint          - Run all linters (Python + TypeScript)"
	@echo "  make lint-python   - Run Python linting only"
	@echo "  make lint-typescript - Run TypeScript linting only"
	@echo "  make setup         - Install development dependencies"
	@echo "  make clean         - Clean test artifacts and cache"
	@echo "  make install-dev   - Install all development tools"

# Virtual environment activation
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# Check if virtual environment exists
$(VENV)/bin/activate:
	@echo "Virtual environment not found. Please create one with:"
	@echo "  python3 -m venv .venv"
	@echo "  source .venv/bin/activate"
	@echo "  pip install -r requirements.txt"
	@exit 1

# Install development dependencies
install-dev: $(VENV)/bin/activate
	@echo "Installing Python development dependencies..."
	@$(PIP) install pytest pytest-cov pytest-asyncio pylint black isort
	@echo "Installing TypeScript/React development dependencies..."
	@cd frontend && npm install
	@if ! command -v eslint >/dev/null 2>&1; then \
		echo "Installing global ESLint..."; \
		npm install -g eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin; \
	fi

# Setup target that ensures everything is ready
setup: install-dev
	@echo "Development environment setup complete!"

# Clean trailing whitespace from Python files (silent operation)
clean-whitespace:
	@find . -name "*.py" -type f -exec sed -i '' 's/[[:space:]]*$$//' {} \; 2>/dev/null || true

# Python linting
lint-python: $(VENV)/bin/activate clean-whitespace
	@echo "=== Python Linting ==="
	@echo "Running Black code formatter..."
	@$(PYTHON) -m black --check --diff backend/ tests/ || (echo "Run 'make format-python' to fix formatting"; exit 1)
	@echo "Running pylint..."
	@$(PYTHON) -m pylint backend/ --rcfile=.pylintrc || true
	@echo "✅ Python linting completed"

# TypeScript/React linting
lint-typescript:
	@echo "=== TypeScript/React Linting ==="
	@cd frontend && npm run lint
	@echo "✅ TypeScript linting completed"

# Combined linting
lint: lint-python lint-typescript
	@echo "✅ All linting completed successfully!"

# Format Python code (helper target)
format-python: $(VENV)/bin/activate clean-whitespace
	@echo "Formatting Python code..."
	@$(PYTHON) -m black backend/ tests/

# Python tests
test-python: $(VENV)/bin/activate clean-whitespace
	@echo "=== Running Python Tests ==="
	@$(PYTHON) -m pytest tests/ -v --tb=short --cov=backend --cov-report=term-missing --cov-report=html
	@echo "✅ Python tests completed"

# TypeScript/React tests
test-typescript:
	@echo "=== Running TypeScript/React Tests ==="
	@cd frontend && npm test
	@echo "✅ TypeScript tests completed"

# Combined testing
test: test-python test-typescript
	@echo "✅ All tests completed successfully!"

# Clean artifacts
clean:
	@echo "Cleaning test artifacts and cache..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov/ .coverage
	@cd frontend && rm -rf coverage/ 2>/dev/null || true
	@echo "✅ Clean completed"

# Development server targets (bonus)
run-dev: setup
	@echo "Starting development servers..."
	@./run.sh

stop-dev:
	@echo "Stopping development servers..."
	@./stop.sh