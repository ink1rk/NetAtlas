# API Structure

Base URL: `https://<host>/api/v1`  
Auth: `Authorization: Bearer <access_token>`  
Content-Type: `application/json`  
All mutating endpoints that could affect **network devices** are absent. Mutations allowed only for NetAtlas itself (users, seeds, jobs, credentials vault, exports).

## Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Username/password → tokens |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Revoke refresh |
| GET | `/auth/me` | Current user + roles |

## Devices / Inventory

| Method | Path | Description |
|--------|------|-------------|
| GET | `/devices` | List/filter/paginate |
| GET | `/devices/{id}` | Detail + interfaces |
| GET | `/devices/{id}/interfaces` | Interfaces |
| GET | `/devices/{id}/neighbors` | LLDP/CDP neighbors |
| GET | `/devices/{id}/fdb` | FDB table |
| GET | `/devices/{id}/arp` | ARP table |
| GET | `/devices/{id}/routes` | Routing table (read) |
| GET | `/devices/{id}/metrics` | Latest + history |
| GET | `/search` | Unified search |

## Topology

| Method | Path | Description |
|--------|------|-------------|
| GET | `/topology/graph` | Nodes + edges for Cytoscape |
| GET | `/topology/cable-path` | Path between two endpoints |
| GET | `/links` | Link inventory |

## Discovery

| Method | Path | Description |
|--------|------|-------------|
| GET | `/discovery/seeds` | Seed list |
| POST | `/discovery/seeds` | Add seed (CIDR/IP + credential ref) |
| DELETE | `/discovery/seeds/{id}` | Remove seed |
| POST | `/discovery/jobs` | Start discovery job |
| GET | `/discovery/jobs` | Job list |
| GET | `/discovery/jobs/{id}` | Job status/stats |
| WS | `/ws/discovery/{id}` | Live progress |

## Snapshots / Diff

| Method | Path | Description |
|--------|------|-------------|
| GET | `/snapshots` | List |
| GET | `/snapshots/{id}` | Detail/summary |
| POST | `/snapshots/diff` | Body: `{left_id, right_id}` |

## IPAM

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ipam/prefixes` | Prefix tree |
| POST | `/ipam/prefixes` | Register prefix (NetAtlas DB only) |
| GET | `/ipam/prefixes/{id}/addresses` | Used/free/conflict |
| GET | `/ipam/conflicts` | Conflict list |

## VMware / Docker

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vmware/hosts` | ESXi hosts |
| GET | `/vmware/hosts/{id}/vms` | VMs |
| GET | `/vmware/hosts/{id}/datastores` | Datastores |
| GET | `/docker/hosts` | Docker hosts |
| GET | `/docker/hosts/{id}/containers` | Containers |
| GET | `/docker/hosts/{id}/networks` | Networks |

## Export

| Method | Path | Description |
|--------|------|-------------|
| POST | `/export` | `{format, scope}` → async job or file |
| GET | `/export/{job_id}` | Download when ready |

## Admin / System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness (DB/Redis/MQ) |
| GET | `/audit` | Audit log (RBAC) |
| CRUD | `/credentials` | Encrypted credential profiles |
| CRUD | `/users` | User admin (RBAC) |

## Error Envelope

```json
{
  "error": {
    "code": "WRITE_OPERATION_FORBIDDEN",
    "message": "Device configuration changes are not allowed",
    "request_id": "…"
  }
}
```

## Pagination

`?page=1&page_size=50` → `{items, total, page, page_size}`.
