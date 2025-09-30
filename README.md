<div align="center">
  <img src="sysmanage-logo.svg" alt="SysManage" width="330"/>
</div>

# SysManage Server

[![CI/CD Pipeline](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml/badge.svg)](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Node.js Version](https://img.shields.io/badge/node.js-20.x-green.svg)](https://nodejs.org)
[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting](https://img.shields.io/badge/pylint-10.00/10-brightgreen.svg)](https://github.com/PyCQA/pylint)
[![TypeScript](https://img.shields.io/badge/eslint-0%20warnings-brightgreen.svg)]()
[![Security: bandit](https://img.shields.io/badge/bandit-passing-brightgreen.svg)](https://github.com/PyCQA/bandit) [![Security: semgrep](https://img.shields.io/badge/semgrep-scan-brightgreen.svg)](https://semgrep.dev/) [![Security: safety](https://img.shields.io/badge/safety-passing-brightgreen.svg)](https://pypi.org/project/safety/) [![Security: snyk](https://img.shields.io/badge/snyk-monitored-brightgreen.svg)](https://snyk.io/) [![Security: trufflehog](https://img.shields.io/badge/trufflehog-clean-brightgreen.svg)](https://github.com/trufflesecurity/trufflehog)
[![Backend Test Coverage](https://img.shields.io/badge/backend%20test%20coverage-65%25-yellow.svg)]()
[![Frontend Test Coverage](https://img.shields.io/badge/frontend%20test%20coverage-12%25-red.svg)]()
[![UI Tests](https://img.shields.io/badge/ui%20tests-passing-brightgreen.svg)]()
[![Performance Tests](https://img.shields.io/badge/performance%20tests-optimized-brightgreen.svg)]()
[![Artillery Load Tests](https://img.shields.io/badge/artillery-0ms-brightgreen.svg)]()

A modern, cross-platform system monitoring and management platform with real-time WebSocket communication, built with FastAPI and React.

## 📚 Documentation

**Complete documentation is available at [sysmanage.org](https://sysmanage.org)**

### Quick Links
- **🚀 [Getting Started](https://sysmanage.org/docs/getting-started/)** - Quick start guide and tutorials
- **🛠️ [Installation Guide](https://sysmanage.org/docs/server/installation.html)** - Complete server installation
- **⚙️ [Configuration](https://sysmanage.org/docs/server/configuration.html)** - Server configuration options
- **📋 [Reports & PDF Generation](https://sysmanage.org/docs/server/reports.html)** - Comprehensive reporting system
- **🧪 [Testing & Playwright](https://sysmanage.org/docs/server/testing.html)** - Testing strategy and E2E testing
- **🔐 [Security](https://sysmanage.org/docs/security/)** - Security features and best practices
- **🔌 [API Reference](https://sysmanage.org/docs/api/)** - REST API and WebSocket documentation

## Overview

SysManage is a comprehensive system management solution that allows you to monitor and manage remote servers across multiple operating systems (Linux, Windows, macOS, FreeBSD, and OpenBSD). The system consists of:

- **Backend API**: FastAPI-based REST API with WebSocket support
- **Frontend Web UI**: Modern React application built with Vite
- **Database**: PostgreSQL with Alembic migrations and UUID-based primary keys for enhanced security
- **Real-time Communication**: WebSocket-based agent communication

### Key Features

- 🔄 Real-time agent status monitoring via WebSockets
- 📊 System metrics and health monitoring
- 📋 **Comprehensive Reporting System with PDF Generation**
- 🔐 JWT-based authentication with mTLS security
- 👥 Multi-user management system with RBAC
- 🏢 Fleet-based host organization
- 🖥️ Cross-platform agent support with auto-discovery
- 📱 Responsive web interface
- 🌍 Multi-language support (14 languages including RTL support)
- 🛡️ Enterprise-grade security scanning and monitoring
- ⚡ Ubuntu Pro Master Key management for bulk enrollment

## Prerequisites

- **Python**: 3.11 or 3.12 (Python 3.13 not yet supported)
- **Node.js**: 20.x or higher (22.13+ recommended for Artillery performance testing)
- **PostgreSQL**: 14 or higher
- **OS**: Linux, macOS, Windows, FreeBSD, or OpenBSD

> **🔐 Security Note**: After installation, you MUST run the `scripts/sysmanage_secure_installation` script to create the initial admin user and configure unique security tokens for your installation.

**📖 For detailed platform-specific installation instructions, visit [sysmanage.org/docs/server/installation.html](https://sysmanage.org/docs/server/installation.html)**

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/bceverly/sysmanage.git
cd sysmanage

# 2. Create virtual environment
python3.11 -m venv .venv  # or python3.12
source .venv/bin/activate
# Note: On BSD systems (FreeBSD, OpenBSD, NetBSD), use: . .venv/bin/activate

# 3. Setup database (see documentation for detailed instructions)
# Install PostgreSQL and SQLite3 (required before installing Python dependencies)
# FreeBSD users also need: sudo pkg install py311-sqlite3
# Create PostgreSQL database and user
# Configure /etc/sysmanage.yaml

# 4. Install dependencies
# Note: Rust is required for some Python dependencies
# Install Rust: https://rustup.rs/ or use your package manager
# FreeBSD users also need: sudo pkg install jpeg-turbo tiff freetype2 png webp lcms2
pip install --upgrade pip
pip install -r requirements.txt

# 5. Run migrations
alembic upgrade head

# 6. Install frontend dependencies
cd frontend && npm install && cd ..

# 7. Run secure installation script (REQUIRED for new installations)
scripts/sysmanage_secure_installation
# This script creates the initial admin user and sets unique security tokens

# 8. Start the application
make start
```

## Development

### Running Tests
```bash
# Run all tests
make test

# Backend tests only
python -m pytest tests/ -v

# Frontend tests only
cd frontend && npm test

# End-to-End tests (optional - requires Playwright)
# Note: Playwright may not be available on all platforms (e.g., OpenBSD)
npm run test:e2e

# Linting
make lint
```

### Code Quality Standards
- **Backend**: Perfect 10.00/10 PyLint score, Black formatting, Bandit security scanning
- **Frontend**: 0 ESLint warnings, TypeScript strict mode
- **Security**: Comprehensive automated security scanning (Bandit, Semgrep, Safety, Snyk, TruffleHog)
- **Testing**: 1,432 Python tests (pytest), 63 TypeScript tests (Vitest), optional E2E tests (Playwright) - 100% coverage both frontend and backend

## Project Structure

```
sysmanage/
├── backend/                 # FastAPI backend
│   ├── api/                # REST API endpoints
│   ├── auth/               # JWT authentication
│   ├── persistence/        # Database models and ORM
│   └── websocket/          # WebSocket communication
├── frontend/               # React frontend (Vite-based)
│   ├── src/Components/     # React components
│   └── src/Pages/          # Page components
├── tests/                  # Backend Python tests
├── alembic/                # Database migrations
└── requirements.txt        # Python dependencies
```

## API Documentation

When running the backend server, interactive API documentation is available at:
- **Swagger UI**: http://localhost:6443/docs
- **ReDoc**: http://localhost:6443/redoc

## Internationalization

SysManage supports 14 languages with full localization:

| Language | Code | Status |
|----------|------|--------|
| English | `en` | ✅ Complete |
| Spanish | `es` | ✅ Complete |
| French | `fr` | ✅ Complete |
| German | `de` | ✅ Complete |
| Italian | `it` | ✅ Complete |
| Portuguese | `pt` | ✅ Complete |
| Dutch | `nl` | ✅ Complete |
| Japanese | `ja` | ✅ Complete |
| Simplified Chinese | `zh_CN` | ✅ Complete |
| Traditional Chinese | `zh_TW` | ✅ Complete |
| Korean | `ko` | ✅ Complete |
| Russian | `ru` | ✅ Complete |
| Arabic | `ar` | ✅ Complete (RTL) |
| Hindi | `hi` | ✅ Complete |

## Security

SysManage implements enterprise-grade security features:

### 🔐 Secure Installation
- **Secure Installation Script**: `scripts/sysmanage_secure_installation` must be run on new installations
- **Unique Security Tokens**: Generates unique JWT secrets and salt values for each installation
- **Initial Admin User**: Creates the first administrative user with secure credentials
- **Configuration Hardening**: Applies security best practices to configuration files

### 🛡️ Database Security
- **UUID-Based Primary Keys**: All database tables use UUIDs instead of sequential integers
- **Prevents Information Leakage**: UUIDs eliminate predictable ID enumeration attacks
- **Replay Attack Protection**: Non-sequential identifiers prevent replay attacks
- **Enhanced Privacy**: Resource URLs cannot be easily guessed or scraped
- **GDPR Compliance**: Supports data anonymization through non-correlatable identifiers

### 🔒 Core Security Features
- **Authentication**: JWT-based with token rotation and refresh
- **Authorization**: Role-based access control (RBAC)
- **Communication**: Mutual TLS (mTLS) for agent connections
- **Encryption**: End-to-end encrypted communication
- **Scanning**: Automated security vulnerability scanning
- **Policies**: Configurable password policies and account security

**📖 For complete security documentation, visit [sysmanage.org/docs/security/](https://sysmanage.org/docs/security/)**

## Deployment

### Development
```bash
# Backend
uvicorn backend.main:app --reload --host 0.0.0.0 --port 6443

# Frontend
cd frontend && npm run dev
```

### Production
```bash
# Backend
uvicorn backend.main:app --host 0.0.0.0 --port 6443 --workers 4

# Frontend
cd frontend && npm run build
# Serve built files from frontend/build/
```

**📖 For detailed deployment instructions, visit [sysmanage.org/docs/server/deployment.html](https://sysmanage.org/docs/server/deployment.html)**

## 🧪 Testing

This project uses a **dual conftest architecture** for optimal test performance and database isolation:

- **`/tests/conftest.py`**: Integration tests with full schema (Alembic migrations)
- **`/tests/api/conftest.py`**: Fast API tests with minimal dependencies (manual models)

### Running Tests

```bash
# Run all tests (backend + frontend + UI + performance)
make test

# Run specific test suites
make test-python           # Backend tests only
make test-typescript       # Frontend tests only
make test-playwright        # UI tests only
make test-performance       # Performance tests (Artillery + Playwright + regression analysis)

# Individual test files
python -m pytest tests/api/test_packages.py -v
python -m pytest tests/api/ -q --tb=no
```

#### 🚀 Performance Testing

SysManage includes comprehensive performance testing with multi-OS support:

- **Artillery Load Testing** - API response times, throughput, error rates
- **Playwright Performance** - UI metrics, Core Web Vitals, cross-browser testing
- **Regression Detection** - Statistical analysis with tolerance bands (±15%)
- **Multi-Platform** - Linux, macOS, Windows (FreeBSD supported, OpenBSD partial)

```bash
# Run performance tests locally
make test-performance

# Performance requirements
npm install -g artillery@latest  # For load testing
playwright install               # For browser automation
```

**📊 For detailed performance testing documentation, see [PERFORMANCE_TESTING.md](PERFORMANCE_TESTING.md)**

### ⚠️ Adding New Database Models

**CRITICAL**: When adding new models, update BOTH conftest files:

1. **Main conftest** (automatic): `alembic revision --autogenerate -m "Add NewModel"`
2. **API conftest** (manual): Add SQLite-compatible model definition if API tests need it

**SQLite Compatibility Rules**:
- ✅ Use `Integer` primary keys (not `BigInteger`) for auto-increment
- ✅ Use `String` instead of `Text` for better performance
- ✅ Omit timezone info in `DateTime` columns

See `TESTING.md` for detailed guidelines.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Ensure all tests pass and linting is clean (`make test lint`)
5. Submit a pull request

**📖 For detailed contribution guidelines, visit [sysmanage.org/docs/](https://sysmanage.org/docs/)**

## Related Projects

- **[SysManage Agent](https://github.com/bceverly/sysmanage-agent)** - Cross-platform agent for system monitoring
- **[Documentation Site](https://github.com/bceverly/sysmanage-docs)** - Source for sysmanage.org documentation

## License

This project is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for details.

## Support

- **📖 Documentation**: [sysmanage.org](https://sysmanage.org)
- **🐛 Issues**: [GitHub Issues](https://github.com/bceverly/sysmanage/issues)
- **💬 Discussions**: [GitHub Discussions](https://github.com/bceverly/sysmanage/discussions)