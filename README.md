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
- 🔐 JWT-based authentication with token rotation and login security
- 👥 Multi-user management system with account locking
- 🏢 Fleet-based host organization
- 🖥️ Cross-platform agent support with auto-discovery
- 📱 Responsive web interface
- 🌍 Multi-language support (11 languages)
- 🛡️ Comprehensive security with encrypted communication
- ⚙️ Agent configuration management from server
- 🔍 Automatic server discovery for new agents
- 🧪 Comprehensive test coverage (61 tests)

### Internationalization

SysManage supports multiple languages with full localization of the user interface and system messages. The following languages are natively supported:

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
| Korean | `ko` | ✅ Complete |
| Russian | `ru` | ✅ Complete |

The system automatically detects the browser's preferred language and falls back to English if the preferred language is not supported. Users can manually change the language using the language selector in the navigation bar.

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

### Required Directories and Permissions

The SysManage server requires certain directories to exist with proper permissions for normal operation:

#### Certificate Storage Directory
**Default location**: `/etc/sysmanage/certs/` (configurable via `certificates.path` in configuration)

```bash
# Create certificate directory with proper permissions
sudo mkdir -p /etc/sysmanage/certs
sudo chown sysmanage:sysmanage /etc/sysmanage/certs
sudo chmod 0755 /etc/sysmanage/certs
```

**Required permissions**:
- **Directory**: `0755` (owner read/write/execute, group and others read/execute)
- **Private keys**: `0600` (owner read/write only)
- **Certificates**: `0644` (owner read/write, others read-only)

#### Configuration Directory
**Default location**: `/etc/sysmanage.yaml`

```bash
# Create configuration file with proper permissions
sudo touch /etc/sysmanage.yaml
sudo chown sysmanage:sysmanage /etc/sysmanage.yaml  
sudo chmod 0600 /etc/sysmanage.yaml
```

#### Log Directory (Optional)
If using file-based logging, ensure the log directory is writable:

```bash
# Create log directory
sudo mkdir -p /var/log/sysmanage
sudo chown sysmanage:sysmanage /var/log/sysmanage
sudo chmod 0755 /var/log/sysmanage
```

#### Service User Account
For production deployments, create a dedicated service user:

```bash
# Create sysmanage user and group
sudo useradd -r -s /bin/false -d /opt/sysmanage -c "SysManage Server" sysmanage
```

**Note**: During development and testing, the application automatically detects test environments and uses temporary directories to avoid permission issues.

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

### Agent Approval System

SysManage implements a manual approval system for agent registration to ensure only authorized hosts can connect to your server:

#### How it Works

1. **Agent Registration**: When a new agent attempts to connect, it registers with the server but is initially set to "pending" status
2. **Manual Approval Required**: Agents with "pending" or "rejected" status cannot establish WebSocket connections
3. **Administrative Approval**: Administrators must manually approve new agents through the web interface
4. **Connection Authorization**: Only "approved" agents can connect and send heartbeat/monitoring data

#### Approval Workflow

1. **Initial Connection**: New agents register via `/host/register` endpoint
2. **Pending Status**: Host is created with `approval_status="pending"`  
3. **Admin Review**: Navigate to Hosts page in the web UI to see pending registrations
4. **Approve/Reject**: Use the approve (✓) or reject (✗) buttons for each pending host
5. **Agent Access**: Approved agents can establish WebSocket connections and begin monitoring

#### Important Notes

- **Existing approved agents** continue to work normally when server is updated
- **Deleted hosts** that reconnect are automatically set back to "pending" status requiring re-approval  
- **Rejected agents** cannot connect until their status is changed to "approved"
- **Database persistence** ensures approval status survives server restarts

### Mutual TLS (mTLS) Security

SysManage implements mutual TLS authentication to protect against DNS poisoning attacks and agent spoofing:

#### Security Features

1. **Server Authentication**: Agents validate server certificates against stored fingerprints to prevent DNS poisoning and man-in-the-middle attacks
2. **Client Authentication**: Server validates agent certificates to prevent agent spoofing and unauthorized connections
3. **Certificate Pinning**: First connection stores server certificate fingerprint for future validation
4. **Automatic Certificate Management**: Server generates and manages client certificates during host approval

#### How mTLS Works

1. **Initial Registration**: Agent connects via HTTP/HTTPS and registers with pending status
2. **Manual Approval**: Administrator approves the host through web interface
3. **Certificate Generation**: Server automatically generates unique client certificate for approved host
4. **Certificate Retrieval**: Agent fetches certificates via authenticated API call
5. **Secure Connection**: All subsequent WebSocket connections use mutual TLS with certificate validation

#### Certificate Storage

**Server-side certificates** are stored in `/etc/sysmanage/certs/` (configurable):
```
/etc/sysmanage/certs/
├── ca.crt              # Certificate Authority certificate
├── ca.key              # CA private key (restricted permissions)
├── server.crt          # Server certificate
└── server.key          # Server private key (restricted permissions)
```

**Agent-side certificates** are stored in `/etc/sysmanage-agent/` (configurable):
```
/etc/sysmanage-agent/
├── client.crt          # Agent client certificate
├── client.key          # Agent private key (0600 permissions)
├── ca.crt              # CA certificate for server validation
└── server.fingerprint  # Server certificate fingerprint for pinning
```

#### Certificate Lifecycle

- **Generation**: Certificates are generated when hosts are approved
- **Validation**: Both server and agent certificates are validated on each connection
- **Rotation**: Certificates can be regenerated by re-fetching from the server
- **Revocation**: Certificates can be revoked by clearing host approval status

#### Security Benefits

- **DNS Poisoning Protection**: Agents validate server identity via certificate fingerprints
- **Agent Spoofing Prevention**: Only hosts with valid certificates can connect
- **Man-in-the-Middle Protection**: Full TLS encryption with mutual certificate validation
- **Identity Verification**: Each certificate is cryptographically tied to specific hostname and host ID

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
- **WebSocket**: `/api/agent/connect` - Secure agent communication with authentication
- **Configuration Management**: `/api/config/push` - Push configuration updates to agents

### Agent Auto-Discovery

SysManage includes an automatic discovery system that allows agents to find and configure themselves with available servers on the network:

#### How Auto-Discovery Works

1. **Server Beacon Service**: The SysManage server runs a UDP beacon service on port 31337 that responds to discovery requests from agents
2. **Agent Discovery Process**: When an agent starts without a configuration file, it:
   - Sends UDP broadcast discovery requests on port 31337 to common network broadcast addresses
   - Listens for server announcement broadcasts on port 31338
   - Evaluates discovered servers using a scoring system (SSL preference, local network preference)
   - Automatically configures itself with the best available server
3. **Configuration Distribution**: The server provides default configuration parameters to new agents during discovery
4. **Fallback Support**: If discovery fails, agents can still be manually configured using traditional configuration files

#### Discovery Message Flow

```
Agent Discovery Process:
1. Agent broadcasts: "Looking for SysManage server" → Port 31337
2. Server responds: "SysManage server available" + config → Agent
3. Agent selects best server and writes configuration file
4. Agent connects via WebSocket using discovered configuration

Server Announcement Process:
1. Server periodically broadcasts: "SysManage server available" → Port 31338
2. Agents listen and collect server information
3. Agents update their server lists and select best options
```

### Required Network Ports

For full SysManage functionality, ensure the following ports are open in your firewall:

#### Server Ports (Inbound)
- **TCP 6443** (or configured port) - HTTPS API server
- **TCP 7443** (or configured port) - HTTPS Web UI
- **UDP 31337** - Discovery beacon service (responds to agent discovery requests)

#### Agent Ports (Outbound)  
- **TCP 6443** (or server port) - HTTPS connections to server API and WebSocket
- **UDP 31337** - Discovery requests to servers
- **UDP 31338** - Listen for server announcements

#### Optional Ports
- **TCP 5432** - PostgreSQL database (if running on separate server)
- **TCP 6443** - HTTP API server (fallback if no SSL certificates)
- **TCP 3000** - HTTP Web UI (development/fallback mode)

### Swagger Documentation
When running the backend, visit: http://localhost:6443/docs

## WebSocket Architecture

The system uses secure WebSocket connections for real-time communication between agents and the server:

- **Secure Authentication**: Agents must obtain connection tokens before establishing WebSocket connections
- **Connection Management**: Agent registration with manual approval system - new agents require administrator approval before establishing connections. Includes heartbeat monitoring with connection timeouts
- **Message Types**: System info, commands, heartbeats, configuration updates, errors
- **Message Security**: HMAC validation ensures message integrity and prevents tampering
- **Broadcasting**: Send commands to all agents, specific platforms, or individual hosts
- **Configuration Push**: Server can push configuration updates to agents in real-time
- **Fault Tolerance**: Automatic cleanup of failed connections and rate limiting protection

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
