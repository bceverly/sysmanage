<div align="center">
  <img src="sysmanage-logo.svg" alt="SysManage" width="330"/>
</div>

# SysManage Server

[![CI/CD Pipeline](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml/badge.svg)](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Node.js Version](https://img.shields.io/badge/node.js-20.x-green.svg)](https://nodejs.org)
[![License](https://img.shields.io/badge/license-BSD%202--Clause-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting](https://img.shields.io/badge/linting-pylint-blue.svg)](https://github.com/PyCQA/pylint)

A modern, cross-platform system monitoring and management platform with real-time WebSocket communication, built with FastAPI and React.

## Overview

SysManage is a comprehensive system management solution that allows you to monitor and manage remote servers across multiple operating systems (Linux, Windows, macOS, FreeBSD, and OpenBSD). The system consists of:

- **Backend API**: FastAPI-based REST API with WebSocket support
- **Frontend Web UI**: Modern React application built with Vite
- **Database**: PostgreSQL with Alembic migrations
- **Real-time Communication**: WebSocket-based agent communication

### Key Features

- 🔄 Real-time agent status monitoring via WebSockets
- 📊 System metrics and health monitoring
- 🔐 JWT-based authentication with token rotation
- 👥 Multi-user management system
- 🏢 Fleet-based host organization
- 🖥️ Cross-platform agent support
- 📱 Responsive web interface
- 🧪 Comprehensive test coverage (61 tests)

## Prerequisites

### System Requirements
- **Python**: 3.12 or higher
- **Node.js**: 20.x or higher
- **PostgreSQL**: 14 or higher
- **OS**: Linux, macOS, Windows, FreeBSD, or OpenBSD

### Required Tools
```bash
# Python tools (automatically installed)
pip install -r requirements.txt

# Node.js tools (automatically installed)
npm install
```

## Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/bceverly/sysmanage.git
cd sysmanage

# Create Python virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Backend Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Setup
```bash
# Install PostgreSQL 14+
# Create database and user
createdb sysmanage
createuser sysmanage_user

# Run database migrations
alembic upgrade head
```

### 4. Install Frontend Dependencies
```bash
cd frontend
npm install
```

### 5. Configuration

#### SSL Certificates (Development)
For HTTPS development, place your SSL certificates in:
```
~/dev/certs/sysmanage.org/
├── cert.pem
└── privkey.pem
```

If certificates are not found, the system will automatically fall back to HTTP on localhost.

#### Environment Configuration
Create `/etc/sysmanage.yaml` or set environment variables:
```yaml
database_url: "postgresql://sysmanage_user:password@localhost/sysmanage"
secret_key: "your-secret-key-here"
api_host: "localhost"
api_port: 6443
frontend_host: "localhost"
frontend_port: 7443
```

## Development Workflow

### Running the Application

#### Backend API Server
```bash
# Development mode with auto-reload
uvicorn backend.main:app --reload --host 0.0.0.0 --port 6443

# Production mode
uvicorn backend.main:app --host 0.0.0.0 --port 6443
```

#### Frontend Development Server
```bash
cd frontend
npm run dev
```
The frontend will be available at:
- HTTPS: https://sysmanage.org:7443 (if SSL certs exist)
- HTTP: http://localhost:3000 (fallback)

### Testing

#### Run All Tests
```bash
make test
```

#### Individual Test Suites
```bash
# Backend tests (Python)
python -m pytest tests/ -v

# Frontend tests (TypeScript/React)
cd frontend && npm test

# Test with coverage
python -m pytest tests/ --cov=backend --cov-report=html
```

#### Linting
```bash
# Python linting
python -m pylint backend/

# TypeScript/React linting
cd frontend && npm run lint
```

### Database Management

#### Creating Migrations
```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

#### Migration Commands
```bash
# Show migration history
alembic history

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>
```

## Project Structure

```
sysmanage/
├── backend/                 # FastAPI backend
│   ├── api/                # REST API endpoints
│   ├── auth/               # JWT authentication
│   ├── config/             # Configuration management
│   ├── persistence/        # Database models and ORM
│   ├── websocket/          # WebSocket communication
│   └── main.py             # FastAPI application entry point
├── frontend/               # React frontend (Vite-based)
│   ├── src/
│   │   ├── Components/     # React components
│   │   ├── Pages/          # Page components
│   │   ├── Services/       # API client services
│   │   └── __tests__/      # Frontend tests
│   ├── vite.config.ts      # Vite configuration
│   └── package.json        # Node.js dependencies
├── tests/                  # Backend Python tests
├── alembic/                # Database migrations
├── requirements.txt        # Python dependencies
└── Makefile               # Build automation
```

## API Documentation

### Authentication Flow

1. **Login**: `POST /login` - Returns JWT token
2. **Authenticated Requests**: Include `Authorization: Bearer <token>` header
3. **Token Rotation**: Each successful request returns a new token in `X_Reauthorization` header
4. **Security**: Tokens are single-use and automatically deny-listed after use

### API Endpoints

- **Authentication**: `/login`, `/logout`
- **Users**: `/users`, `/users/{id}`
- **Hosts**: `/hosts`, `/hosts/{id}`, `/host/by_fqdn/{fqdn}`
- **Fleet Management**: `/fleet`, `/fleet/{id}`
- **WebSocket**: `/ws/{agent_id}` - Real-time agent communication

### Swagger Documentation
When running the backend, visit: http://localhost:6443/docs

## WebSocket Architecture

The system uses WebSocket connections for real-time communication between agents and the server:

- **Connection Management**: Automatic agent registration and heartbeat monitoring
- **Message Types**: System info, commands, heartbeats, errors
- **Broadcasting**: Send commands to all agents, specific platforms, or individual hosts
- **Fault Tolerance**: Automatic cleanup of failed connections

## Deployment

### Production Build

#### Backend
```bash
# Install production dependencies
pip install -r requirements.txt

# Run with production settings
uvicorn backend.main:app --host 0.0.0.0 --port 6443 --workers 4
```

#### Frontend
```bash
cd frontend
npm run build
# Serve the built files from frontend/build/
```

### Docker Support
```bash
# Build and run with Docker Compose
docker-compose up -d
```

## Development Guidelines

- **Code Style**: Black formatting, pylint for Python; ESLint + Prettier for TypeScript
- **Testing**: Maintain >90% test coverage for critical paths
- **Commits**: Use conventional commit format with Claude Code co-author attribution
- **Security**: No hardcoded secrets, secure JWT implementation, input validation

## Troubleshooting

### Common Issues

1. **SSL Certificate Errors**: Ensure certificates exist in correct path or disable HTTPS
2. **Database Connection**: Verify PostgreSQL is running and credentials are correct
3. **Port Conflicts**: Check that ports 6443 (API) and 7443 (frontend) are available
4. **Node.js Version**: Ensure Node.js 20.x is installed

### Logs
- Backend logs: Console output from uvicorn
- Frontend logs: Browser developer console
- Database logs: PostgreSQL logs

## Internationalization (i18n)

SysManage supports multiple languages through comprehensive internationalization:

### Supported Languages
- **English** (en) - Default
- **French** (fr) - Français  
- **Japanese** (ja) - 日本語

### Translation Files Location

**Frontend (React/TypeScript):**
```
frontend/public/locales/
├── en/translation.json
├── fr/translation.json
└── ja/translation.json
```

**Backend (Python):**
```
backend/i18n/locales/
├── en/LC_MESSAGES/messages.po
├── fr/LC_MESSAGES/messages.po
└── ja/LC_MESSAGES/messages.po
```

### Adding New Languages

1. **Frontend**: Create new JSON files in `frontend/public/locales/{language}/translation.json`
2. **Backend**: Create new `.po` files in `backend/i18n/locales/{language}/LC_MESSAGES/messages.po`
3. **Compile translations**: Run `msgfmt messages.po -o messages.mo` in the LC_MESSAGES directory
4. **Update language selector**: Add language to `frontend/src/Components/LanguageSelector.tsx`

### Using Translations

**Frontend (React):**
```typescript
import { useTranslation } from 'react-i18next';

const MyComponent = () => {
  const { t } = useTranslation();
  return <div>{t('nav.dashboard')}</div>;
};
```

**Backend (Python):**
```python
from backend.i18n import _

raise HTTPException(status_code=401, detail=_("Invalid username or password"))
```

### Language Detection
- **Frontend**: Automatically detects browser language, falls back to stored preference
- **Backend**: Language can be set programmatically via `set_language()` function

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Ensure all tests pass and linting is clean
5. Submit a pull request

## License

This project is licensed under the BSD 2-Clause License. See [LICENSE](LICENSE) for details.
