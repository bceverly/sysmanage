<div align="center">
  <img src="sysmanage-logo.svg" alt="SysManage" width="330"/>
</div>

# SysManage Server

[![CI/CD Pipeline](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml/badge.svg)](https://github.com/bceverly/sysmanage/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Node.js Version](https://img.shields.io/badge/node.js-20.x-green.svg)](https://nodejs.org)
[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![Linting](https://img.shields.io/badge/pylint-10.00/10-brightgreen.svg)](https://github.com/PyCQA/pylint)
[![TypeScript](https://img.shields.io/badge/eslint-0%20warnings-brightgreen.svg)]()
[![Backend Test Coverage](https://img.shields.io/badge/backend%20test%20coverage-62%25-yellow.svg)]()
[![Frontend Test Coverage](https://img.shields.io/badge/frontend%20test%20coverage-13%25-red.svg)]()

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
- 🌍 Multi-language support (14 languages including RTL support)
- 🛡️ Comprehensive security with encrypted communication and configurable password policies
- ⚙️ Agent configuration management from server
- 🔍 Automatic server discovery for new agents
- 🧪 Comprehensive test coverage (258 Python tests, 24 TypeScript tests)

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
| Traditional Chinese | `zh_TW` | ✅ Complete |
| Korean | `ko` | ✅ Complete |
| Russian | `ru` | ✅ Complete |
| Arabic | `ar` | ✅ Complete (RTL) |
| Hindi | `hi` | ✅ Complete |

The system automatically detects the browser's preferred language and falls back to English if the preferred language is not supported. Users can manually change the language using the language selector in the navigation bar.

**RTL Support**: Arabic language includes full right-to-left (RTL) text support with automatic theme switching and proper text direction handling.

## Prerequisites

### System Requirements
- **Python**: 3.11 or 3.12 (Note: Python 3.13 is NOT yet supported due to package compatibility)
- **Node.js**: 20.x or higher
- **PostgreSQL**: 14 or higher
- **OS**: Linux, macOS, Windows, FreeBSD, or OpenBSD

### Platform-Specific Installation Instructions

#### Linux (Ubuntu/Debian)
```bash
# Update package manager
sudo apt update

# Install Python (3.11 or 3.12 ONLY - not 3.13)
# For Ubuntu 22.04 through 24.10:
sudo apt install python3.11 python3.11-venv python3.11-dev python3-pip

# For Ubuntu with Python 3.12 (if available):
# sudo add-apt-repository ppa:deadsnakes/ppa
# sudo apt update
# sudo apt install python3.12 python3.12-venv python3.12-dev python3-pip

# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PostgreSQL 14+
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Install build tools and development libraries for Python packages
sudo apt install build-essential libffi-dev libssl-dev libpq-dev

# Additional packages needed for Python 3.13+ compatibility
sudo apt install libuv1-dev python3-setuptools
```

#### Linux (Ubuntu 25.04 or newer) - Building Python 3.12 from Source

Ubuntu 25.04+ only ships with Python 3.13, which is not yet compatible with many packages. You must build Python 3.12 from source:

```bash
# Install build dependencies
sudo apt install build-essential libssl-dev zlib1g-dev libbz2-dev \
    libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev \
    libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev \
    python3-openssl git libpq-dev libuv1-dev

# Download and build Python 3.12
cd /tmp
wget https://www.python.org/ftp/python/3.12.7/Python-3.12.7.tgz
tar -xf Python-3.12.7.tgz
cd Python-3.12.7

# Configure and build (this may take 10-15 minutes)
./configure --enable-optimizations --with-ensurepip=install
make -j$(nproc)
sudo make altinstall

# Verify installation
python3.12 --version

# Return to your project directory
cd ~/dev/sysmanage

# Create virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Upgrade pip to latest version
pip install --upgrade pip

# Install remaining Ubuntu packages
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PostgreSQL 14+
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Linux (CentOS/RHEL/Fedora)
```bash
# Install Python 3.12+ (use available version)
sudo dnf install python3 python3-devel python3-pip

# If python3.12 is available in your distribution, you can also try:
# sudo dnf install python3.12 python3.12-devel python3-pip

# Install Node.js 20.x
curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
sudo dnf install -y nodejs

# Install PostgreSQL 14+
sudo dnf install postgresql postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Install build tools and development libraries
sudo dnf groupinstall "Development Tools"
sudo dnf install libffi-devel openssl-devel postgresql-devel

# Additional packages needed for Python 3.13+ compatibility
sudo dnf install libuv-devel python3-setuptools
```

#### macOS
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.12+
brew install python@3.12

# Install Node.js 20.x
brew install node@20
brew link node@20

# Install PostgreSQL 14+
brew install postgresql@14
brew services start postgresql@14

# Build tools are included with Xcode Command Line Tools
xcode-select --install
```

#### Windows
```powershell
# Install Python 3.12 (RECOMMENDED) from https://python.org/downloads/
# AVOID Python 3.13 - many packages don't have Windows binaries yet
# Make sure to check "Add Python to PATH" during installation

# Install Node.js 20.x from https://nodejs.org/
# Download and run the Windows installer

# Install PostgreSQL 14+ from https://postgresql.org/download/windows/
# Download and run the Windows installer

# Install Git for Windows (includes build tools)
# Download from https://git-scm.com/download/win

# Install Windows Build Tools (if needed for native packages)
# Note: windows-build-tools package is deprecated and may not work
# Instead, install Visual Studio Build Tools from Microsoft:
# https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
```

#### FreeBSD
```bash
# Update package manager
sudo pkg update

# Install Python 3.12+
sudo pkg install python312 py312-pip py312-sqlite3

# Install Node.js 20.x
sudo pkg install node20 npm

# Install PostgreSQL 14+
sudo pkg install postgresql14-server postgresql14-client
sudo service postgresql enable
sudo service postgresql initdb
sudo service postgresql start

# Install build tools
sudo pkg install gcc cmake make
```

#### OpenBSD
```bash
# Update package manager
doas pkg_add -u

# Install Python 3.12+
doas pkg_add python-3.12 py3-pip

# Install Node.js 20.x
doas pkg_add node

# Install PostgreSQL 14+
doas pkg_add postgresql-server postgresql-client
doas rcctl enable postgresql
doas su - _postgresql -c "initdb -D /var/postgresql/data"
doas rcctl start postgresql

# Install build tools (required for cryptography packages)
doas pkg_add rust gcc cmake gmake pkgconf
```

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
**Default locations** (configurable via `certificates.path` in configuration):
- **Linux/macOS/BSD**: `/etc/sysmanage/certs/`
- **Windows**: `C:\ProgramData\SysManage\certs\`

```bash
# Create certificate directory with proper permissions (Linux/macOS/BSD)
sudo mkdir -p /etc/sysmanage/certs
sudo chown sysmanage:sysmanage /etc/sysmanage/certs
sudo chmod 0755 /etc/sysmanage/certs
```

```powershell
# Create certificate directory (Windows)
mkdir "C:\ProgramData\SysManage\certs"
icacls "C:\ProgramData\SysManage\certs" /grant "sysmanage:(OI)(CI)F" /T
```

**Required permissions**:
- **Directory**: `0755` (owner read/write/execute, group and others read/execute)
- **Private keys**: `0600` (owner read/write only)
- **Certificates**: `0644` (owner read/write, others read-only)

#### Configuration Directory
**Default locations**:
- **Linux/macOS/BSD**: `/etc/sysmanage.yaml`
- **Windows**: `C:\ProgramData\SysManage\sysmanage.yaml`

```bash
# Create configuration file with proper permissions (Linux/macOS/BSD)
sudo touch /etc/sysmanage.yaml
sudo chown sysmanage:sysmanage /etc/sysmanage.yaml  
sudo chmod 0600 /etc/sysmanage.yaml
```

```powershell
# Create configuration file (Windows)
New-Item -Path "C:\ProgramData\SysManage\sysmanage.yaml" -ItemType File -Force
icacls "C:\ProgramData\SysManage\sysmanage.yaml" /grant "sysmanage:F" /inheritance:r
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

# Create Python virtual environment (use specific version)
python3.11 -m venv .venv  # Or python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
                           # On OpenBSD: . .venv/bin/activate

# Upgrade pip to latest version
pip install --upgrade pip
```

### 2. Install Backend Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Setup

#### PostgreSQL Installation and Configuration

After installing PostgreSQL (see platform-specific instructions above), set up the database and user:

**For most platforms (Linux, macOS, FreeBSD):**
```bash
# Switch to the postgres user
sudo -u postgres psql

# In the PostgreSQL prompt, create the database and user
# NOTE: Using credentials from sysmanage-dev.yaml - CHANGE FOR PRODUCTION!
CREATE USER sysmanage WITH PASSWORD 'abc123';
CREATE DATABASE sysmanage OWNER sysmanage;
GRANT ALL PRIVILEGES ON DATABASE sysmanage TO sysmanage;

# Grant schema permissions (required for Alembic migrations)
\c sysmanage
GRANT ALL ON SCHEMA public TO sysmanage;

# Exit PostgreSQL
\q
```

**For OpenBSD (using doas instead of sudo):**

First, configure doas properly for PostgreSQL access. As root, create or edit `/etc/doas.conf`:

```bash
# Edit /etc/doas.conf as root
echo "# Allow wheel group members to run commands as any user" >> /etc/doas.conf
echo "permit :wheel" >> /etc/doas.conf
echo "" >> /etc/doas.conf
echo "# Allow wheel group to run commands as _postgresql user (for database setup)" >> /etc/doas.conf
echo "permit :wheel as _postgresql" >> /etc/doas.conf
```

Or manually add these lines to `/etc/doas.conf`:
```
# Allow wheel group members to run commands as any user
permit :wheel

# Allow wheel group to run commands as _postgresql user (for database setup)
permit :wheel as _postgresql
```

Then ensure your user is in the wheel group:
```bash
# Check if you're in the wheel group:
groups

# If not in wheel group, add yourself (as root):
# usermod -G wheel yourusername
```

Now you can set up the database:
```bash
# Switch to the _postgresql user and connect to the default postgres database
doas -u _postgresql psql postgres

# In the PostgreSQL prompt, create the database and user
# NOTE: Using credentials from sysmanage-dev.yaml - CHANGE FOR PRODUCTION!
CREATE USER sysmanage WITH PASSWORD 'abc123';
CREATE DATABASE sysmanage OWNER sysmanage;
GRANT ALL PRIVILEGES ON DATABASE sysmanage TO sysmanage;

# Grant schema permissions (required for Alembic migrations)
\c sysmanage
GRANT ALL ON SCHEMA public TO sysmanage;

# Exit PostgreSQL
\q
```

**Alternative method if doas configuration is not desired:**
```bash
# Become root first
su -
# Then switch to _postgresql user and connect to postgres database
su - _postgresql
psql postgres
# (then run the same SQL commands above)
```

**For Windows:**

After installing PostgreSQL from the Windows installer, you can access the database using either:

1. **SQL Shell (psql) - Recommended:**
```cmd
# Open "SQL Shell (psql)" from Start Menu or run from PostgreSQL's bin directory
# Default connection parameters are usually correct (localhost:5432, postgres database, postgres user)
# Press Enter for defaults, then enter the password you set during installation

# In the PostgreSQL prompt, create the database and user
# NOTE: Using credentials from sysmanage-dev.yaml - CHANGE FOR PRODUCTION!
CREATE USER sysmanage WITH PASSWORD 'abc123';
CREATE DATABASE sysmanage OWNER sysmanage;
GRANT ALL PRIVILEGES ON DATABASE sysmanage TO sysmanage;

# Grant schema permissions (required for Alembic migrations)
\c sysmanage
GRANT ALL ON SCHEMA public TO sysmanage;

# Exit PostgreSQL
\q
```

2. **Command Prompt (if psql is in PATH):**
```cmd
# Connect to PostgreSQL (replace 'postgres' with your admin user if different)
psql -U postgres -h localhost

# Then run the same SQL commands as above
```

3. **pgAdmin 4 (GUI option):**
   - Open pgAdmin 4 (installed with PostgreSQL)
   - Connect to your local PostgreSQL server
   - Create database "sysmanage"
   - Create user "sysmanage" with password "abc123"
   - Grant all privileges on database to user

**Security Notes:**
- ⚠️ The default development configuration uses password `abc123` (from `sysmanage-dev.yaml`) - **NEVER use this in production**
- 🔐 For production: Change the password in both PostgreSQL AND your `sysmanage.yaml` configuration file
- 🛡️ Consider using PostgreSQL's peer authentication for local connections
- 🔒 Restrict database access to localhost only in `postgresql.conf`

#### Test Database Connection
```bash
# Test the connection with the development credentials (matches sysmanage-dev.yaml)
PGPASSWORD=abc123 psql -U sysmanage -d sysmanage -h localhost -c "SELECT version();"
```

#### Run Database Migrations
```bash
# After configuring sysmanage.yaml with your database credentials
# Run Alembic migrations to create the schema
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
Create the configuration file (or `sysmanage-dev.yaml` for development):
- **Linux/macOS/BSD**: `/etc/sysmanage.yaml` 
- **Windows**: `C:\ProgramData\SysManage\sysmanage.yaml`
```yaml
api:
  host: "localhost"
  port: 8080

database:
  user: "sysmanage"
  password: "abc123"  # MATCHES development database setup above - CHANGE FOR PRODUCTION!
  host: "localhost"
  port: 5432
  name: "sysmanage"

security:
  password_salt: "GENERATE_A_NEW_BASE64_STRING"  # Generate with: openssl rand -base64 32
  admin_userid: "admin@yourdomain.com"  # Change to your admin email
  admin_password: "CHANGE_THIS_PASSWORD"  # Set a strong admin password
  jwt_secret: "GENERATE_A_NEW_JWT_SECRET"  # Generate with: openssl rand -base64 32
  jwt_algorithm: "HS256"
  jwt_auth_timeout: 6000
  jwt_refresh_timeout: 60000
  
  # Password Policy Configuration (optional - defaults shown)
  password_policy:
    min_length: 8                    # Minimum password length
    max_length: 128                  # Maximum password length
    require_uppercase: true          # Require at least one uppercase letter
    require_lowercase: true          # Require at least one lowercase letter
    require_numbers: true            # Require at least one number
    require_special: true            # Require at least one special character
    special_characters: "!@#$%^&*()_+-=[]{}|;:,.<>?" # Allowed special characters
    min_character_types: 3           # Minimum different character types required
    prevent_username_in_password: true # Prevent username/email in password

webui:
  host: "localhost"
  port: 3000
```

**Important Security Steps:**
1. 🔑 Generate new secrets: `openssl rand -base64 32`
2. 🔐 Use strong passwords (minimum 12 characters, mixed case, numbers, symbols)
3. 📝 Store production configuration with restricted permissions:
   - **Linux/macOS/BSD**: `/etc/sysmanage.yaml` (`chmod 600 /etc/sysmanage.yaml`)
   - **Windows**: `C:\ProgramData\SysManage\sysmanage.yaml` (restrict access to sysmanage service account)
4. 🚫 Never commit configuration files with real passwords to version control

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

# Run using make commands
make test     # Run all tests with coverage
make lint     # Run all linting (Python + TypeScript)
make dev      # Start development servers
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

**Server-side certificates** are stored with restricted permissions (configurable):

**Linux/macOS/BSD**: `/etc/sysmanage/certs/`
```
/etc/sysmanage/certs/
├── ca.crt              # Certificate Authority certificate
├── ca.key              # CA private key (0600 permissions)
├── server.crt          # Server certificate for HTTPS
└── server.key          # Server private key (0600 permissions)
```

**Windows**: `C:\ProgramData\SysManage\certs\`
```
C:\ProgramData\SysManage\certs\
├── ca.crt              # Certificate Authority certificate
├── ca.key              # CA private key (restricted permissions)
├── server.crt          # Server certificate for HTTPS
└── server.key          # Server private key (restricted permissions)
```

**Agent-side certificates** are stored with restricted permissions (configurable):

**Linux/macOS/BSD**: `/etc/sysmanage-agent/`
```
/etc/sysmanage-agent/
├── client.crt          # Agent client certificate  
├── client.key          # Agent private key (0600 permissions)
├── ca.crt              # CA certificate for server validation
└── server.fingerprint  # Server certificate fingerprint for pinning
```

**Windows**: `C:\ProgramData\SysManage\`
```
C:\ProgramData\SysManage\
├── client.crt          # Agent client certificate  
├── client.key          # Agent private key (restricted permissions)
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

## Advanced Security Features

### Dynamic Password Policy System

SysManage includes a comprehensive, configurable password policy system that enforces strong password requirements:

#### Features
- **Configurable Requirements**: Set minimum/maximum length, character type requirements
- **Real-time Validation**: Both client-side and server-side password validation
- **Dynamic Display**: Password requirements are displayed dynamically based on configuration
- **Multi-language Support**: Password validation messages in all 14 supported languages

#### Configuration Options
```yaml
security:
  password_policy:
    min_length: 8                    # Minimum password length (default: 8)
    max_length: 128                  # Maximum password length (default: 128)
    require_uppercase: true          # Require uppercase letters
    require_lowercase: true          # Require lowercase letters
    require_numbers: true            # Require numbers
    require_special: true            # Require special characters
    special_characters: "!@#$%^&*()_+-=[]{}|;:,.<>?"  # Allowed special chars
    min_character_types: 3           # Minimum character types required
    prevent_username_in_password: true # Prevent username/email in password
```

### Email Configuration

SysManage supports email functionality for password reset, notifications, and system alerts. Configure SMTP settings in the `email` section of your configuration file.

#### Basic Configuration
```yaml
email:
  # Enable or disable email functionality
  enabled: true
  
  # SMTP server configuration
  smtp:
    host: "smtp.gmail.com"              # SMTP server hostname
    port: 587                           # SMTP port (587 for STARTTLS, 465 for SSL)
    use_tls: true                       # Enable STARTTLS (recommended for port 587)
    use_ssl: false                      # Enable SSL/TLS (for port 465)
    username: "your-email@gmail.com"    # SMTP authentication username
    password: "your-app-password"       # SMTP authentication password
    timeout: 30                         # Connection timeout in seconds
  
  # Default sender information
  from_address: "noreply@your-domain.com"  # Default sender email address
  from_name: "SysManage System"            # Default sender name
  
  # Email template settings
  templates:
    subject_prefix: "[SysManage]"          # Prefix for all email subjects
```

#### Common SMTP Configurations

**Gmail (with App Password)**
```yaml
email:
  enabled: true
  smtp:
    host: "smtp.gmail.com"
    port: 587
    use_tls: true
    use_ssl: false
    username: "your-email@gmail.com"
    password: "your-16-digit-app-password"
```
> **Note**: For Gmail, you need to enable 2-Factor Authentication and generate an App Password. Visit [Google App Passwords](https://support.google.com/accounts/answer/185833) for instructions.

**Microsoft Office 365**
```yaml
email:
  enabled: true
  smtp:
    host: "smtp-mail.outlook.com"
    port: 587
    use_tls: true
    use_ssl: false
    username: "your-email@yourdomain.com"
    password: "your-password"
```

**Microsoft Exchange (On-Premises)**
```yaml
email:
  enabled: true
  smtp:
    host: "mail.yourdomain.com"
    port: 587
    use_tls: true
    use_ssl: false
    username: "your-email@yourdomain.com"
    password: "your-password"
```

**Postfix (Self-Hosted)**
```yaml
email:
  enabled: true
  smtp:
    host: "localhost"
    port: 25
    use_tls: false
    use_ssl: false
    username: ""    # Leave empty for localhost/no-auth
    password: ""    # Leave empty for localhost/no-auth
```

#### Testing Email Configuration

Once configured, you can test your email settings through the SysManage web interface:

1. Navigate to **Settings** → **Integrations**
2. Find the **Email Configuration** card
3. Click **Test Configuration** 
4. Enter a test email address
5. Check your inbox for the test message

#### Profile UI Enhancement
The user profile interface has been reorganized for better security management:
- **Account Information Tab**: Email change functionality
- **Personal Information Tab**: Name and profile details
- **Security Information Tab**: Password change with real-time validation

### Security Warning System

SysManage automatically detects and warns about security configuration issues:
- **Default Credentials Detection**: Warns when default admin credentials are in use
- **Default JWT Secret Detection**: Alerts for default cryptographic secrets
- **Default Password Salt Detection**: Identifies default password salts
- **Mixed Security States**: Warns about inconsistent security configurations
- **Visual Security Banner**: Prominent warnings displayed in the UI until resolved

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

### API Routing Conventions

SysManage follows a consistent API routing pattern:

#### Unauthenticated Endpoints (no `/api` prefix)
These endpoints do not require JWT authentication and are available for initial setup:
- `/login` - User authentication
- `/refresh` - Token refresh
- `/host/register` - Agent registration
- `/certificates/server-fingerprint` - Server certificate fingerprint for agent setup
- `/certificates/ca-certificate` - CA certificate for agent setup
- `/agent/auth` - Agent authentication

#### Authenticated Endpoints (`/api` prefix)
All endpoints requiring JWT authentication are prefixed with `/api`:
- `/api/users/*` - User management
- `/api/hosts/*` - Host management (except registration)
- `/api/fleet/*` - Fleet management
- `/api/certificates/client/*` - Client certificate management
- `/api/security/*` - Security status and configuration
- `/api/config/*` - Configuration management
- `/api/diagnostics/*` - System diagnostics
- `/api/profiles/*` - User profile management
- `/api/updates/*` - System updates
- `/api/scripts/*` - Script management
- `/api/tags/*` - Tag management
- `/api/queue/*` - Message queue management

This convention ensures clear separation between public and secure endpoints, making it easier for frontend developers and agent implementers to understand authentication requirements.

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

## Security Scanning Infrastructure

SysManage implements comprehensive automated security scanning to protect against vulnerabilities and ensure code quality:

### Continuous Integration Security Tools

Our GitHub Actions CI/CD pipeline includes multiple security scanning tools that run automatically on every push and pull request:

#### Backend Security (Python)
- **[Bandit](https://bandit.readthedocs.io/)** - Static security analysis for Python code, detecting common vulnerabilities
- **[Safety](https://pypi.org/project/safety/)** - Vulnerability scanning for Python dependencies
- **[Semgrep](https://semgrep.dev/)** - Multi-language static analysis with OWASP Top 10 rule sets

#### Frontend Security (JavaScript/React)
- **[ESLint Security](https://github.com/eslint-community/eslint-plugin-security)** - Security-focused linting for JavaScript/TypeScript
- **[eslint-plugin-no-unsanitized](https://github.com/mozilla/eslint-plugin-no-unsanitized)** - Prevents DOM XSS vulnerabilities
- **[Snyk](https://snyk.io/)** - Vulnerability scanning for npm dependencies
- **[npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit)** - Built-in npm security auditing

#### Cross-Language Security Tools
- **[CodeQL](https://codeql.github.com/)** - GitHub's semantic code analysis for both Python and JavaScript
- **[TruffleHog](https://github.com/trufflesecurity/trufflehog)** - Secrets detection to prevent credential leaks

### Security Workflow Files

Our security infrastructure is implemented through multiple GitHub Actions workflows:

- **`.github/workflows/security.yml`** - Comprehensive security scanning with Semgrep, Snyk, Safety, and secrets detection
- **`.github/workflows/codeql.yml`** - GitHub's native CodeQL security analysis
- **`.github/workflows/ci.yml`** - Enhanced with security artifact uploads

### Local Security Testing

Developers can run security scans locally before committing:

```bash
# Backend security scanning
python -m bandit -r backend/ -f screen
pip freeze | safety check --stdin

# Frontend security scanning  
cd frontend && npx eslint --config eslint.security.config.js src/

# Local comprehensive security scanning
make security          # Run all security tools (comprehensive)
make security-full     # Run all security tools (same as above)
make security-python   # Python-only security (Bandit + Safety)
make security-frontend # Frontend-only security (ESLint)
make security-secrets  # Basic secrets detection
```

### Security Configuration Files

- **`frontend/eslint.security.config.js`** - Dedicated ESLint configuration for security-focused scanning
- **`frontend/package.json`** - Includes security-focused ESLint plugins
- **`.github/workflows/security.yml`** - Main security scanning workflow
- **`.github/workflows/codeql.yml`** - CodeQL configuration for Python and JavaScript analysis

### Security Reporting

All security scan results are:
- **Integrated with GitHub Security Tab** - Centralized vulnerability management
- **Available as CI Artifacts** - Downloadable reports for each scan
- **SARIF Compatible** - Standardized security report format
- **Automatically Updated** - Weekly scheduled scans for dependency vulnerabilities

### Free for Non-Enterprise GitHub

All security scanning tools used are available at no cost for public repositories and non-enterprise GitHub accounts, providing enterprise-grade security without licensing costs.

## Development Guidelines

- **Code Quality**: Perfect 10.00/10 PyLint score, 0 ESLint warnings, Black formatting
- **Testing**: Maintain comprehensive test coverage (258 Python tests, 24 TypeScript tests)
- **Dependencies**: All production dependencies properly managed in requirements.txt
- **Commits**: Use conventional commit format with Claude Code co-author attribution
- **Security**: No hardcoded secrets, secure JWT implementation, configurable password policies, comprehensive automated security scanning
- **Internationalization**: All user-visible strings must be externalized and translated

## Troubleshooting

### Common Issues

1. **SSL Certificate Errors**: Ensure certificates exist in correct path or disable HTTPS
2. **Database Connection**: Verify PostgreSQL is running and credentials are correct
3. **Port Conflicts**: Check that ports 6443 (API) and 7443 (frontend) are available
4. **Node.js Version**: Ensure Node.js 20.x is installed
5. **Python Package Build Errors**: If you encounter build errors when installing Python packages:
   - **Missing libpq-fe.h**: Install `libpq-dev` (Ubuntu/Debian) or `postgresql-devel` (RHEL/Fedora)
   - **httptools build errors**: Install `libuv1-dev` (Ubuntu/Debian) or `libuv-devel` (RHEL/Fedora)
   - **Python 3.13+ compatibility**: Some packages may not yet support Python 3.13, especially on Windows. Consider using Python 3.11 or 3.12:
     ```bash
     # Ubuntu/Debian
     sudo apt install python3.11 python3.11-venv python3.11-dev
     python3.11 -m venv .venv
     
     # Or use deadsnakes PPA for newer Python versions
     sudo add-apt-repository ppa:deadsnakes/ppa
     sudo apt update
     sudo apt install python3.12 python3.12-venv python3.12-dev
     python3.12 -m venv .venv
     ```
     
     **For Windows**: Download Python 3.12 from https://python.org/downloads/windows/ and reinstall. Python 3.13 has limited Windows binary support for many packages.

### Logs
- Backend logs: Console output from uvicorn
- Frontend logs: Browser developer console
- Database logs: PostgreSQL logs

## Internationalization (i18n)

SysManage supports multiple languages through comprehensive internationalization:

### Supported Languages
- **English** (en) - Default
- **Spanish** (es) - Español
- **French** (fr) - Français
- **German** (de) - Deutsch
- **Italian** (it) - Italiano
- **Portuguese** (pt) - Português
- **Dutch** (nl) - Nederlands
- **Japanese** (ja) - 日本語
- **Simplified Chinese** (zh_CN) - 简体中文
- **Traditional Chinese** (zh_TW) - 繁體中文
- **Korean** (ko) - 한국어
- **Russian** (ru) - Русский
- **Arabic** (ar) - العربية (RTL)
- **Hindi** (hi) - हिन्दी

### Translation Files Location

**Frontend (React/TypeScript):**
```
frontend/public/locales/
├── en/translation.json
├── es/translation.json
├── fr/translation.json
├── de/translation.json
├── it/translation.json
├── pt/translation.json
├── nl/translation.json
├── ja/translation.json
├── zh_CN/translation.json
├── zh_TW/translation.json
├── ko/translation.json
├── ru/translation.json
├── ar/translation.json
└── hi/translation.json
```

**Backend (Python):**
```
backend/i18n/locales/
├── en/LC_MESSAGES/messages.po
├── es/LC_MESSAGES/messages.po
├── fr/LC_MESSAGES/messages.po
├── de/LC_MESSAGES/messages.po
├── it/LC_MESSAGES/messages.po
├── pt/LC_MESSAGES/messages.po
├── nl/LC_MESSAGES/messages.po
├── ja/LC_MESSAGES/messages.po
├── zh_CN/LC_MESSAGES/messages.po
├── zh_TW/LC_MESSAGES/messages.po
├── ko/LC_MESSAGES/messages.po
├── ru/LC_MESSAGES/messages.po
├── ar/LC_MESSAGES/messages.po
└── hi/LC_MESSAGES/messages.po
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

This project is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for details.
