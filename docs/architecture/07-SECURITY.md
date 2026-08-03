# Security Architecture

## Threat Model (summary)

| Threat | Control |
|--------|---------|
| Credential theft from DB | AES-256-GCM, key from env/file, never logged |
| Device compromise via NetAtlas | Read-only collectors + command allow-list |
| Privilege escalation | RBAC permissions, least privilege roles |
| Session hijack | Short JWT, rotating refresh, HTTPS only |
| CSRF | SameSite cookies + CSRF token when cookie auth used |
| Brute force | Rate limit on `/auth/login` |
| Supply chain / CDN | Offline-vendored frontend, pinned images |
| Audit gaps | Append-only audit_events |

## Secrets

- Master key: `NETATLAS_MASTER_KEY` (32-byte base64) loaded at process start  
- Credential profiles store `nonce || ciphertext`  
- Key rotation via `key_version`; re-encrypt job supported  

## Roles (default)

| Role | Permissions |
|------|-------------|
| Viewer | read inventory, topology, IPAM, snapshots, metrics |
| Operator | Viewer + start discovery, manage seeds, export |
| Admin | Operator + users, credentials, system settings |

## TLS

Nginx terminates TLS. Installer generates self-signed or uses provided certs. HTTP redirects to HTTPS. HSTS enabled.

## Logging

Structured JSON logs. Secrets redacted by filter. Correlation `request_id` / `job_id`.
