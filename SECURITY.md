# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

Email security issues to the repository maintainers via GitHub Security Advisories.

Do **not** open public issues for undisclosed vulnerabilities.

## Security Guarantees (MVP)

- Device interaction is strictly **read-only** (SNMP SET and mutate SSH commands are blocked).
- Credential profiles are encrypted at rest with AES-256-GCM.
- TLS termination at Nginx; HTTP redirects to HTTPS.
- JWT (RS256) authentication with RBAC.
- Append-only audit log for security-relevant actions.
- Offline-first: no CDN, analytics, or external telemetry.
