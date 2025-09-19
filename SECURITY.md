# Security Policy

## Supported Versions

We provide security updates for the following versions of SysManage Server:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| 0.9.x   | :white_check_mark: |
| < 0.9   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### 🔒 For Security Issues (DO NOT create public issues)

1. **Email**: Send details to security@sysmanage.org
2. **Include**: 
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if available)

3. **Response Time**: We will acknowledge receipt within 48 hours
4. **Updates**: You'll receive updates every 7 days until resolution

### 📋 For Non-Security Issues

For general bugs and feature requests, please use [GitHub Issues](https://github.com/bceverly/sysmanage/issues).

## Security Measures

### Authentication & Authorization
- JWT-based authentication with refresh tokens
- Argon2 password hashing
- Role-based access control
- Secure session management

### Network Security
- TLS 1.2+ encryption for all communications
- WebSocket Secure (WSS) for real-time communication
- CORS protection
- Rate limiting on API endpoints

### Data Protection
- Database connection encryption
- Sensitive data masking in logs
- Secure configuration file handling
- Environment variable protection

### Infrastructure Security
- Regular security dependency updates via Dependabot
- Comprehensive automated security scanning (see Security Scanning section below)
- Container security best practices
- Principle of least privilege
- Mutual TLS (mTLS) authentication for agent communication
- Certificate-based host approval system

## Security Scanning Infrastructure

SysManage implements enterprise-grade automated security scanning through our CI/CD pipeline to proactively identify and prevent security vulnerabilities:

### Continuous Security Monitoring

All security scans run automatically on:
- **Every push** to main and develop branches
- **Every pull request**
- **Weekly scheduled scans** (Sundays at 2 AM UTC)

### Backend Security Tools (Python)

#### Static Code Analysis
- **[Bandit](https://bandit.readthedocs.io/)** - Detects common security issues in Python code
  - Scans for SQL injection, hardcoded passwords, insecure random generators
  - Identifies unsafe use of eval(), exec(), and shell commands
  - Workflow: `.github/workflows/ci.yml`

- **[Semgrep](https://semgrep.dev/)** - Multi-language static analysis with OWASP Top 10 rules
  - Checks for security anti-patterns and vulnerabilities
  - Uses community rules + OWASP Top 10 rule sets
  - Generates SARIF reports for GitHub Security tab
  - Workflow: `.github/workflows/security.yml`

#### Dependency Vulnerability Scanning
- **[Safety](https://pypi.org/project/safety/)** - Scans Python dependencies for known vulnerabilities
  - Checks against Python security advisories database
  - Identifies vulnerable package versions
  - Generates JSON reports for artifact storage
  - Workflow: `.github/workflows/security.yml`

### Frontend Security Tools (JavaScript/React)

#### Static Code Analysis
- **[ESLint Security Plugin](https://github.com/eslint-community/eslint-plugin-security)** - Security-focused JavaScript/TypeScript linting
  - Detects potential XSS vulnerabilities
  - Identifies insecure random number generation
  - Warns about dangerous RegExp patterns
  - Configuration: `frontend/eslint.security.config.js`
  - Workflow: `.github/workflows/security.yml`

- **[eslint-plugin-no-unsanitized](https://github.com/mozilla/eslint-plugin-no-unsanitized)** - Prevents DOM XSS vulnerabilities
  - Detects unsafe innerHTML usage
  - Identifies unsanitized DOM manipulation
  - Configuration: Integrated in security ESLint config

#### Dependency Vulnerability Scanning
- **[Snyk](https://snyk.io/)** - Advanced vulnerability scanning for npm dependencies
  - Identifies known vulnerabilities in dependencies
  - Provides fix recommendations and upgrade paths
  - Generates SARIF reports for GitHub Security tab
  - Workflow: `.github/workflows/security.yml`

- **[npm audit](https://docs.npmjs.com/cli/v8/commands/npm-audit)** - Built-in npm security auditing
  - Scans package-lock.json for vulnerabilities
  - Provides severity ratings and fix guidance
  - Runs in both CI and security workflows

### Cross-Language Security Tools

#### Semantic Code Analysis
- **[CodeQL](https://codeql.github.com/)** - GitHub's native semantic security analysis
  - Deep analysis of code flow and data dependencies
  - Detects complex security vulnerabilities
  - Supports both Python and JavaScript/TypeScript
  - Integration: SARIF uploads from Semgrep and Snyk

#### Secrets Detection
- **[TruffleHog](https://github.com/trufflesecurity/trufflehog)** - Comprehensive secrets scanning
  - Scans entire git history for leaked credentials
  - Detects API keys, passwords, tokens, certificates
  - Verifies secrets against live services
  - Workflow: `.github/workflows/security.yml`

### Security Workflow Files

Our security infrastructure is organized across multiple workflow files:

```
.github/workflows/
├── security.yml    # Comprehensive security scanning
│   ├── Semgrep (OWASP Top 10 + security rules)
│   ├── Safety (Python dependency scanning)
│   ├── Snyk (npm dependency scanning)
│   ├── ESLint Security (JavaScript security linting)
│   └── TruffleHog (secrets detection)
├── ci.yml          # CI pipeline with security integration
│   ├── Bandit (Python static analysis)
│   ├── npm audit (npm security auditing)
│   └── Security artifact uploads
└── (SARIF uploads to GitHub Security tab)
```

### Local Security Testing

Developers can run security scans locally before committing:

```bash
# Individual security tools
python -m bandit -r backend/ -f screen              # Python static analysis
semgrep scan --config="p/security-audit" --config="p/python" --config="p/owasp-top-ten"  # Multi-language static analysis
pip freeze | safety check --stdin                   # Python dependency check
cd frontend && npm audit                             # npm dependency check
cd frontend && npx eslint --config eslint.security.config.js src/  # JS security lint

# Comprehensive local scanning (if Makefile targets exist)
make security          # Run all security tools
make security-python   # Python-only security tools
make security-frontend # Frontend-only security tools
make security-secrets  # Secrets detection
```

### Security Reporting and Integration

All security scan results are integrated with GitHub's security infrastructure:

- **GitHub Security Tab**: Centralized vulnerability management dashboard
- **SARIF Reports**: Standardized security report format for tool interoperability
- **Security Artifacts**: Downloadable detailed reports for each scan
- **Pull Request Integration**: Security checks block merging if critical issues found
- **Weekly Monitoring**: Scheduled scans catch newly disclosed vulnerabilities

### Security Badge Status

Our README displays real-time security status badges:

- ![Security: bandit](https://img.shields.io/badge/security-bandit-passing-brightgreen.svg) **Bandit**: Python static analysis status
- ![Security: semgrep](https://img.shields.io/badge/security-semgrep-passing-brightgreen.svg) **Semgrep**: Multi-language security analysis
- ![Security: safety](https://img.shields.io/badge/security-safety-passing-brightgreen.svg) **Safety**: Python dependency vulnerability status
- ![Security: snyk](https://img.shields.io/badge/security-snyk-monitored-brightgreen.svg) **Snyk**: npm dependency monitoring status
- ![Security: secrets](https://img.shields.io/badge/security-secrets%20scan-clean-brightgreen.svg) **Secrets**: Repository secrets scan status

## Security Best Practices

### Deployment
- Use HTTPS/TLS certificates from trusted CAs
- Enable firewall rules restricting access
- Regularly update system packages
- Monitor security logs
- Use strong passwords and enable 2FA where possible

### Configuration
- Change default passwords immediately
- Use strong JWT secrets (256-bit minimum)
- Enable secure cookie settings
- Configure appropriate CORS origins
- Set up log monitoring and alerting

### Maintenance
- Apply security updates promptly
- Monitor Dependabot security alerts
- Regular security audits
- Backup and disaster recovery planning

## Responsible Disclosure

We follow responsible disclosure practices:

1. **Initial Report**: Security researcher reports issue privately
2. **Acknowledgment**: We confirm receipt and begin investigation
3. **Investigation**: We assess impact and develop fixes
4. **Fix Development**: Patches are developed and tested
5. **Coordinated Release**: Fix is released with security advisory
6. **Public Disclosure**: Details shared after fix is available

## Bug Bounty

Currently, we do not offer a formal bug bounty program. However, we greatly appreciate security researchers who help improve our security posture and will publicly acknowledge their contributions (with their permission).

## Contact

- **Security Team**: security@sysmanage.org
- **General Contact**: contact@sysmanage.org
- **GitHub Issues**: https://github.com/bceverly/sysmanage/issues
