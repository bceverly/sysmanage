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

For general bugs and feature requests, please use [GitHub Issues](https://github.com/YOUR_USERNAME/sysmanage/issues).

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
- Automated security scanning via Bandit
- Container security best practices
- Principle of least privilege

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
- **GitHub Issues**: https://github.com/YOUR_USERNAME/sysmanage/issues