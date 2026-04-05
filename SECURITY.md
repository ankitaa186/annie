# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Annie, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. Open a [private security advisory](https://github.com/ankitaa186/annie/security/advisories/new) on GitHub
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically within 30 days for critical issues

### Scope

The following are in scope:
- Backend API vulnerabilities
- Authentication/authorization bypasses
- Injection attacks (SQL, command, etc.)
- Sensitive data exposure
- MCP server security issues
- Docker configuration weaknesses

The following are out of scope:
- Denial of service attacks
- Social engineering
- Issues in third-party dependencies (report to the upstream project)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |

## Security Best Practices for Deployers

- Never expose the backend API directly to the internet without authentication (use Cloudflare Access or similar)
- Rotate API keys regularly
- Keep Docker images updated
- Use environment variables for all secrets (never hardcode)
- Review `env.example` for required configuration
- Enable production logging (`ENVIRONMENT=prod`) for audit trails
